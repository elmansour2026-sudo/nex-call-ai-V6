"""
NexCall AI v2 — Modele Agent IA
Chaque agent represente un commercial virtuel specialise dans un service.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Float
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class AgentService(str, enum.Enum):
    # Types de campagne generiques (cas d'usage principal)
    RESILIATION          = "resiliation"
    RELANCE_CLIENT       = "relance_client"
    COMMERCIAL           = "commercial"
    SONDAGE              = "sondage"
    PRISE_RDV            = "prise_rdv"
    # Types specialises assurance (conserves)
    MUTUELLE_SANTE       = "mutuelle_sante"
    ASSURANCE_AUTO       = "assurance_auto"
    ASSURANCE_HABITATION = "assurance_habitation"
    ASSURANCE_PREVOYANCE = "assurance_prevoyance"
    ASSURANCE_DECENNALE  = "assurance_decennale"
    ASSURANCE_MOTO       = "assurance_moto"
    AUTRE                = "autre"


class AgentVoice(str, enum.Enum):
    NOVA    = "nova"
    SHIMMER = "shimmer"
    ALLOY   = "alloy"
    ECHO    = "echo"
    FABLE   = "fable"
    ONYX    = "onyx"


class AgentTone(str, enum.Enum):
    PROFESSIONNEL = "professionnel"
    CHALEUREUX    = "chaleureux"
    DYNAMIQUE     = "dynamique"
    EMPATHIQUE    = "empathique"


class Agent(Base):
    __tablename__ = "agents"

    id               = Column(Integer, primary_key=True, index=True)

    # Identite
    name             = Column(String(64), nullable=False)
    avatar_url       = Column(String(256), nullable=True)   # URL ou emoji
    service          = Column(String(64), nullable=False, index=True)
    description      = Column(Text, nullable=True)

    # Prompt et script
    system_prompt    = Column(Text, nullable=False)
    script_intro     = Column(Text, nullable=True)   # Phrase d'introduction obligatoire
    script_questions = Column(Text, nullable=True)   # JSON: liste de questions
    script_objections= Column(Text, nullable=True)   # JSON: objections + reponses
    business_context = Column(Text, nullable=True)   # Contexte metier specifique
    rules            = Column(Text, nullable=True)   # Regles que l'IA doit suivre (une par ligne)

    # Voix et langue
    voice            = Column(String(32), default=AgentVoice.NOVA.value, nullable=False)
    tone             = Column(String(32), default=AgentTone.PROFESSIONNEL.value, nullable=False)
    language         = Column(String(8), default="fr", nullable=False)

    # Fournisseur IA (flexible — OpenAI ou autre)
    ai_provider      = Column(String(32), default="openai", nullable=False)  # openai|anthropic|mistral|azure|custom
    ai_model         = Column(String(64), default="gpt-4o", nullable=False)  # nom du modele
    ai_temperature   = Column(Float, default=0.7, nullable=False)

    # Telephonie
    ringover_number  = Column(String(32), nullable=True)   # Numero Ringover assigne
    transfer_number  = Column(String(32), nullable=True)   # Numero conseiller humain
    transfer_score   = Column(Integer, default=70, nullable=False)  # Seuil de transfert

    # Statut
    is_active        = Column(Boolean, default=True, nullable=False, index=True)

    # Metriques agregees
    total_calls      = Column(Integer, default=0, nullable=False)
    total_leads      = Column(Integer, default=0, nullable=False)
    total_transfers  = Column(Integer, default=0, nullable=False)
    avg_score        = Column(Float, default=0.0, nullable=False)

    # Timestamps
    created_at       = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    campaigns        = relationship("Campaign", back_populates="agent")
    calls            = relationship("Call", back_populates="agent")

    SERVICE_LABELS = {
        "resiliation":          "Resiliation",
        "relance_client":       "Relance Client",
        "commercial":           "Commercial",
        "sondage":              "Sondage",
        "prise_rdv":            "Prise de RDV",
        "mutuelle_sante":       "Mutuelle Sante",
        "assurance_auto":       "Assurance Auto",
        "assurance_habitation": "Assurance Habitation",
        "assurance_prevoyance": "Assurance Prevoyance",
        "assurance_decennale":  "Assurance Decennale",
        "assurance_moto":       "Assurance Moto",
        "autre":                "Autre",
    }

    SERVICE_AVATARS = {
        "resiliation":          "📋",
        "relance_client":       "🔔",
        "commercial":           "💼",
        "sondage":              "📊",
        "prise_rdv":            "📅",
        "mutuelle_sante":       "💊",
        "assurance_auto":       "🚗",
        "assurance_habitation": "🏠",
        "assurance_prevoyance": "🛡️",
        "assurance_decennale":  "🏗️",
        "assurance_moto":       "🏍️",
        "autre":                "🤖",
    }

    @property
    def service_label(self) -> str:
        return self.SERVICE_LABELS.get(self.service, self.service)

    @property
    def avatar_emoji(self) -> str:
        return self.SERVICE_AVATARS.get(self.service, "🤖")

    @property
    def conversion_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return round(self.total_leads / self.total_calls * 100, 1)

    def to_dict(self) -> dict:
        return {
            "id":               self.id,
            "name":             self.name,
            "avatar_url":       self.avatar_url,
            "avatar_emoji":     self.avatar_emoji,
            "service":          self.service,
            "service_label":    self.service_label,
            "description":      self.description,
            "system_prompt":    self.system_prompt,
            "script_intro":     self.script_intro,
            "script_questions": self.script_questions,
            "script_objections":self.script_objections,
            "business_context": self.business_context,
            "rules":            self.rules,
            "voice":            self.voice,
            "tone":             self.tone,
            "ai_provider":      self.ai_provider,
            "ai_model":         self.ai_model,
            "ai_temperature":   self.ai_temperature,
            "language":         self.language,
            "ringover_number":  self.ringover_number,
            "transfer_number":  self.transfer_number,
            "transfer_score":   self.transfer_score,
            "is_active":        self.is_active,
            "total_calls":      self.total_calls,
            "total_leads":      self.total_leads,
            "total_transfers":  self.total_transfers,
            "avg_score":        self.avg_score,
            "conversion_rate":  self.conversion_rate,
            "created_at":       self.created_at.isoformat() if self.created_at else None,
        }
