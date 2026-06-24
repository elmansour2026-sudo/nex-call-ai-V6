"""
NexCall AI v2 — Modele Campaign (mis a jour)
Ajout FK agent, prospects, scheduled_at, max_concurrent.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Float, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
import enum


def _iso(value):
    """Serialise une valeur date en ISO de maniere defensive.
    Accepte un datetime, une chaine ISO deja formatee, ou None.
    Evite l'erreur 'str object has no attribute isoformat' quand la
    valeur arrive sous forme de chaine (ex: depuis un payload JSON)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return str(value)


class CampaignStatus(str, enum.Enum):
    DRAFT     = "draft"
    SCHEDULED = "scheduled"
    ACTIVE    = "active"
    PAUSED    = "paused"
    COMPLETED = "completed"
    ARCHIVED  = "archived"


class CampaignType(str, enum.Enum):
    INBOUND  = "inbound"
    OUTBOUND = "outbound"


class Campaign(Base):
    __tablename__ = "campaigns"

    id                = Column(Integer, primary_key=True, index=True)
    name              = Column(String(128), nullable=False)
    description       = Column(Text, nullable=True)

    # Type & statut
    type              = Column(String(16), default=CampaignType.OUTBOUND.value, nullable=False)
    status            = Column(String(32), default=CampaignStatus.DRAFT.value, nullable=False, index=True)
    is_active         = Column(Boolean, default=False, nullable=False)

    # Agent IA assigne (v2)
    agent_id          = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)

    # Parametres outbound (v2)
    scheduled_at      = Column(DateTime, nullable=True)     # Date/heure de lancement
    max_concurrent    = Column(Integer, default=3, nullable=False)  # Appels simultanes max

    # Parametres outbound (v3 - mutuelle)
    call_hours_start  = Column(String(8), nullable=True)    # ex "09:00" horaire autorise debut
    call_hours_end    = Column(String(8), nullable=True)    # ex "20:00" horaire autorise fin
    transfer_number   = Column(String(32), nullable=True)   # Numero conseiller humain
    max_attempts      = Column(Integer, default=3, nullable=False)  # Tentatives max par contact
    ring_timeout      = Column(Integer, default=45, nullable=False) # Secondes d'attente avant no-answer

    # Mode test / simulation (v6)
    test_phone_number = Column(String(32), nullable=True)  # Numero de telephone de test

    # Anciens champs conserves pour compatibilite
    target_interest   = Column(String(64), nullable=True)
    target_region     = Column(String(64), nullable=True)
    ai_system_prompt  = Column(Text, nullable=True)
    ivr_message       = Column(Text, nullable=True)

    # Metriques
    total_calls       = Column(Integer, default=0, nullable=False)
    answered_calls    = Column(Integer, default=0, nullable=False)
    missed_calls      = Column(Integer, default=0, nullable=False)
    transferred_calls = Column(Integer, default=0, nullable=False)
    leads_generated   = Column(Integer, default=0, nullable=False)
    conversion_rate   = Column(Float, default=0.0, nullable=False)
    total_prospects   = Column(Integer, default=0, nullable=False)  # v2

    # Timestamps
    started_at        = Column(DateTime, nullable=True)
    ended_at          = Column(DateTime, nullable=True)
    created_at        = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    agent             = relationship("Agent", back_populates="campaigns")
    calls             = relationship("Call", back_populates="campaign")
    prospects         = relationship("Prospect", back_populates="campaign", cascade="all, delete-orphan")

    @property
    def answer_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return round(self.answered_calls / self.total_calls * 100, 1)

    @property
    def progress_pct(self) -> float:
        if self.total_prospects == 0:
            return 0.0
        called = self.answered_calls + self.missed_calls
        return round(called / self.total_prospects * 100, 1)

    def to_dict(self) -> dict:
        return {
            "id":               self.id,
            "name":             self.name,
            "description":      self.description,
            "type":             self.type,
            "status":           self.status,
            "is_active":        self.is_active,
            "agent_id":         self.agent_id,
            "scheduled_at":     _iso(self.scheduled_at),
            "max_concurrent":   self.max_concurrent,
            "call_hours_start": self.call_hours_start,
            "call_hours_end":   self.call_hours_end,
            "transfer_number":  self.transfer_number,
            "max_attempts":     self.max_attempts,
            "ring_timeout":     self.ring_timeout,
            "test_phone_number": self.test_phone_number,
            "target_interest":  self.target_interest,
            "ai_system_prompt": self.ai_system_prompt,
            "total_calls":      self.total_calls,
            "answered_calls":   self.answered_calls,
            "missed_calls":     self.missed_calls,
            "transferred_calls":self.transferred_calls,
            "leads_generated":  self.leads_generated,
            "conversion_rate":  self.conversion_rate,
            "total_prospects":  self.total_prospects,
            "answer_rate":      self.answer_rate,
            "progress_pct":     self.progress_pct,
            "started_at":       _iso(self.started_at),
            "ended_at":         _iso(self.ended_at),
            "created_at":       _iso(self.created_at),
        }
