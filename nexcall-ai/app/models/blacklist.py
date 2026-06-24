"""
NexCall AI v3 — Modele Blacklist (Do Not Call)
Liste des numeros a ne jamais appeler. Bloque automatiquement a l'import.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from app.database import Base


class Blacklist(Base):
    __tablename__ = "blacklist"

    id          = Column(Integer, primary_key=True, index=True)
    phone       = Column(String(32), nullable=False, unique=True, index=True)
    reason      = Column(String(128), nullable=True)   # ex: "demande client", "refus definitif"
    source      = Column(String(64), default="manual", nullable=False)  # manual / call / import
    notes       = Column(Text, nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "phone":      self.phone,
            "reason":     self.reason,
            "source":     self.source,
            "notes":      self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
