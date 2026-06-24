"""
NexCall AI v3 — Modele CallScript (Script Builder)
Script structure d'un agent : intro, qualification, objections, offre, fermeture.
Supporte les variables {{nom}}, {{age}}, {{ancienne_offre}}, {{date_resiliation}}.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.database import Base


class CallScript(Base):
    __tablename__ = "call_scripts"

    id              = Column(Integer, primary_key=True, index=True)
    name            = Column(String(128), nullable=False)
    agent_id        = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=True, index=True)

    # Sections du script (texte avec variables {{...}})
    introduction    = Column(Text, nullable=True)
    qualification   = Column(Text, nullable=True)   # JSON liste de questions
    objections      = Column(Text, nullable=True)   # JSON liste {objection, reponse}
    offer_pitch     = Column(Text, nullable=True)   # Proposition d'offre
    closing         = Column(Text, nullable=True)   # Fermeture

    is_active       = Column(Boolean, default=True, nullable=False)

    created_at      = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    agent           = relationship("Agent", foreign_keys=[agent_id])

    def to_dict(self) -> dict:
        return {
            "id":            self.id,
            "name":          self.name,
            "agent_id":      self.agent_id,
            "introduction":  self.introduction,
            "qualification": self.qualification,
            "objections":    self.objections,
            "offer_pitch":   self.offer_pitch,
            "closing":       self.closing,
            "is_active":     self.is_active,
            "created_at":    self.created_at.isoformat() if self.created_at else None,
        }

    def render(self, variables: dict) -> dict:
        """Remplace les variables {{...}} dans chaque section."""
        def fill(text):
            if not text:
                return text
            for key, val in variables.items():
                text = text.replace("{{" + key + "}}", str(val or ""))
            return text
        return {
            "introduction":  fill(self.introduction),
            "offer_pitch":   fill(self.offer_pitch),
            "closing":       fill(self.closing),
        }
