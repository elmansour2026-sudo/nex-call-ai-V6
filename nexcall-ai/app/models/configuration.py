"""
Modèle Configuration — Stockage des paramètres en BDD
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from app.database import Base


class Configuration(Base):
    __tablename__ = "configurations"

    id          = Column(Integer, primary_key=True, index=True)
    key         = Column(String(128), unique=True, nullable=False, index=True)
    value       = Column(Text, nullable=True)
    category    = Column(String(64), default="general", nullable=False, index=True)
    label       = Column(String(128), nullable=True)
    description = Column(Text, nullable=True)
    is_secret   = Column(Boolean, default=False, nullable=False)
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self, hide_secret: bool = True) -> dict:
        return {
            "key":         self.key,
            "value":       "***" if (self.is_secret and hide_secret) else self.value,
            "category":    self.category,
            "label":       self.label,
            "description": self.description,
            "is_secret":   self.is_secret,
        }
