"""
NexCall AI v3 — Modele Prospect / Contact (mutuelle resiliation)
Un prospect = un client a relancer apres resiliation de sa mutuelle.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class ProspectStatus(str, enum.Enum):
    NOUVEAU            = "nouveau"
    EN_ATTENTE         = "en_attente"
    APPELE             = "appele"
    INTERESSE          = "interesse"
    PAS_INTERESSE      = "pas_interesse"
    NE_REPOND_PAS      = "ne_repond_pas"
    A_RAPPELER         = "a_rappeler"
    TRANSFERE          = "transfere_conseiller"
    REFUS_DEFINITIF    = "refus_definitif"
    DO_NOT_CALL        = "do_not_call"
    # Anciens statuts techniques conserves pour compatibilite v2
    PENDING            = "pending"
    CALLING            = "calling"
    REACHED            = "reached"
    CONVERTED          = "converted"


# Statuts consideres comme "termines" (ne plus appeler)
TERMINAL_STATUSES = {
    ProspectStatus.PAS_INTERESSE.value,
    ProspectStatus.REFUS_DEFINITIF.value,
    ProspectStatus.DO_NOT_CALL.value,
    ProspectStatus.TRANSFERE.value,
    ProspectStatus.CONVERTED.value,
}


class Prospect(Base):
    __tablename__ = "prospects"

    id              = Column(Integer, primary_key=True, index=True)

    # Identite
    first_name      = Column(String(64), nullable=True)
    last_name       = Column(String(64), nullable=True)
    phone           = Column(String(32), nullable=False, index=True)
    email           = Column(String(128), nullable=True)
    birth_date      = Column(String(16), nullable=True)   # DD/MM/YYYY

    # Specifique mutuelle / resiliation
    resiliation_date = Column(String(16), nullable=True)  # Date de resiliation
    old_offer        = Column(String(128), nullable=True) # Ancienne offre mutuelle
    city             = Column(String(64), nullable=True)
    extra_info       = Column(Text, nullable=True)        # Informations client (import)
    notes            = Column(Text, nullable=True)        # Notes manuelles / IA cumulatives

    # Suivi des appels
    status          = Column(String(32), default=ProspectStatus.NOUVEAU.value, nullable=False, index=True)
    attempt_count   = Column(Integer, default=0, nullable=False)
    last_call_at    = Column(DateTime, nullable=True)     # Date du dernier appel
    last_attempt_at = Column(DateTime, nullable=True)
    callback_at     = Column(DateTime, nullable=True)

    # Liens
    campaign_id     = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=True, index=True)
    agent_id        = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True)
    lead_id         = Column(Integer, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)

    # Resultat IA
    ai_result       = Column(String(32), nullable=True)
    ai_notes        = Column(Text, nullable=True)

    is_archived     = Column(Boolean, default=False, nullable=False)

    created_at      = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    campaign        = relationship("Campaign", back_populates="prospects")
    agent           = relationship("Agent", foreign_keys=[agent_id])
    lead            = relationship("Lead", foreign_keys=[lead_id])
    calls           = relationship("Call", back_populates="prospect", foreign_keys="Call.prospect_id")

    STATUS_LABELS = {
        "nouveau":              "Nouveau",
        "en_attente":           "En attente",
        "appele":               "Appele",
        "interesse":            "Interesse",
        "pas_interesse":        "Pas interesse",
        "ne_repond_pas":        "Ne repond pas",
        "a_rappeler":           "A rappeler",
        "transfere_conseiller": "Transfere conseiller",
        "refus_definitif":      "Refus definitif",
        "do_not_call":          "Do not call",
        "pending":              "Nouveau",
        "calling":              "Appel en cours",
        "reached":              "Appele",
        "converted":            "Converti",
    }

    @property
    def full_name(self) -> str:
        parts = [p for p in [self.first_name, self.last_name] if p]
        return " ".join(parts) if parts else self.phone

    @property
    def status_label(self) -> str:
        return self.STATUS_LABELS.get(self.status, self.status)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def to_dict(self) -> dict:
        return {
            "id":               self.id,
            "first_name":       self.first_name,
            "last_name":        self.last_name,
            "full_name":        self.full_name,
            "phone":            self.phone,
            "email":            self.email,
            "birth_date":       self.birth_date,
            "resiliation_date": self.resiliation_date,
            "old_offer":        self.old_offer,
            "city":             self.city,
            "extra_info":       self.extra_info,
            "notes":            self.notes,
            "status":           self.status,
            "status_label":     self.status_label,
            "attempt_count":    self.attempt_count,
            "last_call_at":     self.last_call_at.isoformat() if self.last_call_at else None,
            "last_attempt_at":  self.last_attempt_at.isoformat() if self.last_attempt_at else None,
            "callback_at":      self.callback_at.isoformat() if self.callback_at else None,
            "campaign_id":      self.campaign_id,
            "agent_id":         self.agent_id,
            "lead_id":          self.lead_id,
            "ai_result":        self.ai_result,
            "ai_notes":         self.ai_notes,
            "is_archived":      self.is_archived,
            "created_at":       self.created_at.isoformat() if self.created_at else None,
            "updated_at":       self.updated_at.isoformat() if self.updated_at else None,
        }
