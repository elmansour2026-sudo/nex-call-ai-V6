"""
NexCall AI — Service Configuration dynamique.

Resout la valeur effective d'un parametre : la BDD (table configurations)
est prioritaire, avec repli sur les variables d'environnement (settings).

Permet aussi d'appliquer a chaud les cles sauvegardees aux services en cours
d'execution (RingoverService, AIAgentService) sans redemarrer le serveur.
"""
import logging
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration import Configuration
from app.config import settings

logger = logging.getLogger(__name__)

# Correspondance cle BDD -> attribut settings (repli)
_SETTINGS_FALLBACK = {
    "ringover_api_key":      "RINGOVER_API_KEY",
    "ringover_phone":        "RINGOVER_PHONE_NUMBER",
    "ringover_transfer":     "RINGOVER_TRANSFER_NUMBER",
    "webhook_secret":        "RINGOVER_WEBHOOK_SECRET",
    "openai_api_key":        "OPENAI_API_KEY",
    "openai_model":          "OPENAI_MODEL",
    "tts_voice":             "OPENAI_TTS_VOICE",
    "stt_model":             "OPENAI_STT_MODEL",
    "agent_name":            "AI_AGENT_NAME",
    "company_name":          "AI_COMPANY_NAME",
    "language":              "AI_LANGUAGE",
    "temperature":           "AI_TEMPERATURE",
    "lead_score_threshold":  "LEAD_SCORE_THRESHOLD",
}


class ConfigService:

    async def get_all(self, db: AsyncSession) -> dict[str, str]:
        """Renvoie toutes les valeurs en BDD sous forme {cle: valeur}."""
        result = await db.execute(select(Configuration))
        return {c.key: c.value for c in result.scalars().all() if c.value}

    async def get_value(self, db: AsyncSession, key: str) -> Optional[str]:
        """Valeur effective d'une cle : BDD prioritaire, sinon settings."""
        result = await db.execute(
            select(Configuration).where(Configuration.key == key)
        )
        row = result.scalar_one_or_none()
        if row and row.value not in (None, "", "***"):
            return row.value
        attr = _SETTINGS_FALLBACK.get(key)
        if attr:
            val = getattr(settings, attr, None)
            return str(val) if val not in (None, "") else None
        return None

    async def is_openai_configured(self, db: AsyncSession) -> bool:
        return bool(await self.get_value(db, "openai_api_key"))

    async def is_ringover_configured(self, db: AsyncSession) -> bool:
        return bool(await self.get_value(db, "ringover_api_key"))

    async def apply_to_services(self, db: AsyncSession) -> None:
        """Pousse les cles actives (BDD > settings) dans les services en cours
        d'execution, pour qu'ils prennent effet immediatement sans redemarrage."""
        from app.services.ringover_service import ringover_service
        from app.services.ai_agent import ai_agent

        ringover_key = await self.get_value(db, "ringover_api_key")
        openai_key   = await self.get_value(db, "openai_api_key")

        # Ringover : mise a jour de la cle API a chaud
        try:
            ringover_service.set_api_key(ringover_key)
        except Exception as e:
            logger.warning(f"[config] maj Ringover: {e}")

        # OpenAI / IA : reset des clients pour re-création avec la nouvelle cle
        try:
            ai_agent.set_api_key(openai_key)
        except Exception as e:
            logger.warning(f"[config] maj IA: {e}")

        logger.info("[config] Cles appliquees aux services (Ringover=%s, OpenAI=%s)",
                    bool(ringover_key), bool(openai_key))


config_service = ConfigService()
