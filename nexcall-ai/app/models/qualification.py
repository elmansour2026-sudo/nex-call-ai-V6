"""
NexCall AI v2 — Modele Qualification
Analyse detaillee generee par l'IA apres chaque appel.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class QualificationIntent(str, enum.Enum):
    INTERESTED     = "interested"
    NOT_INTERESTED = "not_interested"
    CALLBACK       = "callback"
    WRONG_NUMBER   = "wrong_number"
    VOICEMAIL      = "voicemail"
    NO_ANSWER      = "no_answer"


class Qualification(Base):
    __tablename__ = "qualifications"

    id              = Column(Integer, primary_key=True, index=True)

    # Lien appel
    call_id         = Column(Integer, ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # Lien prospect/lead
    prospect_id     = Column(Integer, ForeignKey("prospects.id", ondelete="SET NULL"), nullable=True)
    lead_id         = Column(Integer, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)

    # Lien agent
    agent_id        = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)

    # Resultat IA
    intent          = Column(String(32), default=QualificationIntent.NOT_INTERESTED.value, nullable=False, index=True)
    lead_score      = Column(Float, default=0.0, nullable=False)

    # Donnees extraites
    prospect_name   = Column(String(128), nullable=True)
    service         = Column(String(64), nullable=True)
    need_summary    = Column(Text, nullable=True)       # Synthese du besoin
    budget          = Column(String(64), nullable=True)
    urgency         = Column(String(32), nullable=True)
    has_current     = Column(Boolean, nullable=True)    # A deja une assurance/mutuelle
    family_size     = Column(String(32), nullable=True) # Seul / Famille / Couple
    vehicle_type    = Column(String(64), nullable=True) # Pour assurance auto/moto
    property_type   = Column(String(64), nullable=True) # Pour assurance habitation

    # Action decidee
    action          = Column(String(64), nullable=True)  # transfer_agent / callback / close
    callback_date   = Column(String(32), nullable=True)
    transfer_done   = Column(Boolean, default=False, nullable=False)

    # Resume complet
    full_summary    = Column(Text, nullable=True)       # Resume structure en Markdown

    # Timestamps
    created_at      = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    call            = relationship("Call", back_populates="qualification")
    prospect        = relationship("Prospect", foreign_keys=[prospect_id])
    lead            = relationship("Lead", foreign_keys=[lead_id])
    agent           = relationship("Agent", foreign_keys=[agent_id])

    INTENT_LABELS = {
        "interested":     "Interesse",
        "not_interested": "Non interesse",
        "callback":       "Rappel demande",
        "wrong_number":   "Mauvais numero",
        "voicemail":      "Messagerie",
        "no_answer":      "Pas de reponse",
    }

    @property
    def intent_label(self) -> str:
        return self.INTENT_LABELS.get(self.intent, self.intent)

    def to_dict(self) -> dict:
        return {
            "id":            self.id,
            "call_id":       self.call_id,
            "prospect_id":   self.prospect_id,
            "lead_id":       self.lead_id,
            "agent_id":      self.agent_id,
            "intent":        self.intent,
            "intent_label":  self.intent_label,
            "lead_score":    self.lead_score,
            "prospect_name": self.prospect_name,
            "service":       self.service,
            "need_summary":  self.need_summary,
            "budget":        self.budget,
            "urgency":       self.urgency,
            "has_current":   self.has_current,
            "family_size":   self.family_size,
            "vehicle_type":  self.vehicle_type,
            "property_type": self.property_type,
            "action":        self.action,
            "callback_date": self.callback_date,
            "transfer_done": self.transfer_done,
            "full_summary":  self.full_summary,
            "created_at":    self.created_at.isoformat() if self.created_at else None,
        }
