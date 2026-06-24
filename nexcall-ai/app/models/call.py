"""
NexCall AI v2 — Modele Call (mis a jour)
Ajout des FK vers Agent et Prospect.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, Text, Float, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class CallStatus(str, enum.Enum):
    INCOMING    = "incoming"
    RINGING     = "ringing"
    ANSWERED    = "answered"
    IN_PROGRESS = "in_progress"
    TRANSFERRED = "transferred"
    COMPLETED   = "completed"
    MISSED      = "missed"
    FAILED      = "failed"
    VOICEMAIL   = "voicemail"


class CallDirection(str, enum.Enum):
    INBOUND  = "inbound"
    OUTBOUND = "outbound"


class Call(Base):
    __tablename__ = "calls"

    id                  = Column(Integer, primary_key=True, index=True)
    ringover_call_id    = Column(String(128), unique=True, nullable=True, index=True)

    # Numeros
    caller_number       = Column(String(32), nullable=False, index=True)
    called_number       = Column(String(32), nullable=True)

    # Statut et direction
    status              = Column(String(32), default=CallStatus.INCOMING.value, nullable=False)
    direction           = Column(String(16), default=CallDirection.INBOUND.value, nullable=False)

    # Metriques
    duration            = Column(Integer, default=0)
    ring_duration       = Column(Integer, default=0)

    # IVR & IA
    ivr_choice          = Column(String(64), nullable=True)
    transcript          = Column(Text, nullable=True)
    ai_summary          = Column(Text, nullable=True)
    ai_messages_json    = Column(Text, nullable=True)

    # Transfert
    transfer_to         = Column(String(32), nullable=True)
    transferred_at      = Column(DateTime, nullable=True)

    # Relations v1 (conservees)
    campaign_id         = Column(Integer, ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    lead_id             = Column(Integer, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)

    # Relations v2 (nouvelles)
    agent_id            = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    prospect_id         = Column(Integer, ForeignKey("prospects.id", ondelete="SET NULL"), nullable=True)

    # Timestamps
    started_at          = Column(DateTime, default=datetime.utcnow, nullable=False)
    answered_at         = Column(DateTime, nullable=True)
    ended_at            = Column(DateTime, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    campaign            = relationship("Campaign", back_populates="calls")
    lead                = relationship("Lead", back_populates="calls")
    agent               = relationship("Agent", back_populates="calls")
    prospect            = relationship("Prospect", back_populates="calls", foreign_keys=[prospect_id])
    qualification       = relationship("Qualification", back_populates="call", uselist=False)

    @property
    def duration_formatted(self) -> str:
        if not self.duration:
            return "0s"
        m, s = divmod(self.duration, 60)
        return f"{m}m {s:02d}s" if m else f"{s}s"

    def to_dict(self) -> dict:
        return {
            "id":               self.id,
            "ringover_call_id": self.ringover_call_id,
            "caller_number":    self.caller_number,
            "called_number":    self.called_number,
            "status":           self.status,
            "direction":        self.direction,
            "duration":         self.duration,
            "duration_formatted": self.duration_formatted,
            "ivr_choice":       self.ivr_choice,
            "transcript":       self.transcript,
            "ai_summary":       self.ai_summary,
            "transfer_to":      self.transfer_to,
            "campaign_id":      self.campaign_id,
            "lead_id":          self.lead_id,
            "agent_id":         self.agent_id,
            "prospect_id":      self.prospect_id,
            "started_at":       self.started_at.isoformat() if self.started_at else None,
            "answered_at":      self.answered_at.isoformat() if self.answered_at else None,
            "ended_at":         self.ended_at.isoformat() if self.ended_at else None,
            "created_at":       self.created_at.isoformat() if self.created_at else None,
        }
