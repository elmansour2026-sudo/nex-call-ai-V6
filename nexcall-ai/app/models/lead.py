"""
Modèle Lead — Représente un prospect qualifié
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Float, Boolean
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class LeadStatus(str, enum.Enum):
    NEW       = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    HOT       = "hot"
    WARM      = "warm"
    COLD      = "cold"
    CONVERTED = "converted"
    LOST      = "lost"


class LeadInterest(str, enum.Enum):
    AUTO     = "assurance_auto"
    SANTE    = "assurance_sante"
    VIE      = "assurance_vie"
    HABITATION = "assurance_habitation"
    AUTRE    = "autre"


class Lead(Base):
    __tablename__ = "leads"

    id          = Column(Integer, primary_key=True, index=True)

    # Identité
    first_name  = Column(String(64), nullable=True)
    last_name   = Column(String(64), nullable=True)
    phone       = Column(String(32), nullable=False, index=True)
    email       = Column(String(128), nullable=True)

    # Qualification
    interest    = Column(String(64), nullable=True)
    score       = Column(Float, default=0.0, nullable=False)
    status      = Column(String(32), default=LeadStatus.NEW.value, nullable=False, index=True)
    budget      = Column(String(64), nullable=True)     # Budget mensuel approximatif
    urgency     = Column(String(32), nullable=True)     # immediate / 3months / exploring
    notes       = Column(Text, nullable=True)

    # Source
    source      = Column(String(64), default="inbound_call", nullable=False)
    is_archived = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    calls       = relationship("Call", back_populates="lead")

    def __repr__(self) -> str:
        return f"<Lead #{self.id} {self.full_name} [{self.status}] score={self.score}>"

    @property
    def full_name(self) -> str:
        parts = [p for p in [self.first_name, self.last_name] if p]
        return " ".join(parts) if parts else self.phone

    @property
    def score_label(self) -> str:
        if self.score >= 80:
            return "hot"
        elif self.score >= 60:
            return "warm"
        elif self.score >= 30:
            return "qualified"
        else:
            return "cold"

    def recalculate_status(self) -> None:
        """Met à jour le statut basé sur le score"""
        if self.score >= 80:
            self.status = LeadStatus.HOT.value
        elif self.score >= 60:
            self.status = LeadStatus.WARM.value
        elif self.score >= 30:
            self.status = LeadStatus.QUALIFIED.value
        elif self.score > 0:
            self.status = LeadStatus.NEW.value
        else:
            self.status = LeadStatus.COLD.value

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "first_name": self.first_name,
            "last_name":  self.last_name,
            "full_name":  self.full_name,
            "phone":      self.phone,
            "email":      self.email,
            "interest":   self.interest,
            "score":      self.score,
            "score_label": self.score_label,
            "status":     self.status,
            "budget":     self.budget,
            "urgency":    self.urgency,
            "notes":      self.notes,
            "source":     self.source,
            "is_archived": self.is_archived,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
