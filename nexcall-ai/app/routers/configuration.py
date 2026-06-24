"""
NexCall AI — Router Configuration
"""
import logging
from typing import Dict, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.database import get_db
from app.models.configuration import Configuration
from app.services.ringover_service import ringover_service
from app.services.config_service import config_service
from app.config import settings

router = APIRouter(prefix="/api/config", tags=["configuration"])
logger = logging.getLogger(__name__)

SECRET_KEYS = {"ringover_api_key", "openai_api_key", "webhook_secret"}

CATEGORY_MAP = {
    "ringover":     {"ringover_api_key", "ringover_phone", "ringover_transfer", "webhook_secret"},
    "openai":       {"openai_api_key", "openai_model", "tts_voice", "stt_model"},
    "agent":        {"agent_name", "company_name", "language", "temperature"},
    "ivr":          {"ivr_greeting"},
    "leads":        {"lead_score_threshold"},
}


def _get_category(key: str) -> str:
    for category, keys in CATEGORY_MAP.items():
        if key in keys:
            return category
    return "general"


class ConfigSaveRequest(BaseModel):
    configs: Dict[str, str]


@router.get("")
async def get_configuration(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Configuration))
    configs = result.scalars().all()
    return {c.key: c.to_dict() for c in configs}


@router.post("")
async def save_configuration(body: ConfigSaveRequest, db: AsyncSession = Depends(get_db)):
    saved = []
    for key, value in body.configs.items():
        if not key or not isinstance(value, str):
            continue

        result = await db.execute(select(Configuration).where(Configuration.key == key))
        existing = result.scalar_one_or_none()

        if existing:
            # Ne pas écraser un secret avec "***" (masque envoyé par l'UI)
            if existing.is_secret and value == "***":
                continue
            existing.value = value
            existing.updated_at = datetime.utcnow()
        else:
            cfg = Configuration(
                key       = key,
                value     = value,
                category  = _get_category(key),
                is_secret = key in SECRET_KEYS,
            )
            db.add(cfg)
        saved.append(key)

    await db.flush()

    # Appliquer immédiatement les nouvelles clés aux services en cours d'exécution,
    # afin que le statut passe à "Configuré" sans redémarrage du serveur.
    try:
        await config_service.apply_to_services(db)
    except Exception as e:
        logger.warning(f"[config] application aux services: {e}")

    # Recalculer le statut tout de suite pour le renvoyer à l'UI
    status = await _build_status(db)
    return {
        "success": True,
        "saved": saved,
        "message": "Configuration sauvegardée avec succès",
        "status": status,
    }


async def _build_status(db: AsyncSession) -> dict:
    """Construit le statut en consultant la BDD en priorité, puis settings."""
    openai_key   = await config_service.get_value(db, "openai_api_key")
    ringover_key = await config_service.get_value(db, "ringover_api_key")

    openai_model = await config_service.get_value(db, "openai_model") or settings.OPENAI_MODEL
    tts_voice    = await config_service.get_value(db, "tts_voice") or settings.OPENAI_TTS_VOICE
    phone        = await config_service.get_value(db, "ringover_phone") or settings.RINGOVER_PHONE_NUMBER
    transfer     = await config_service.get_value(db, "ringover_transfer") or settings.RINGOVER_TRANSFER_NUMBER
    agent_name   = await config_service.get_value(db, "agent_name") or settings.AI_AGENT_NAME
    company      = await config_service.get_value(db, "company_name") or settings.AI_COMPANY_NAME
    language     = await config_service.get_value(db, "language") or settings.AI_LANGUAGE
    temperature  = await config_service.get_value(db, "temperature") or settings.AI_TEMPERATURE

    ringover_configured = bool(ringover_key)
    openai_configured   = bool(openai_key)

    # Test de connexion seulement si une clé est présente
    ringover_connected = False
    if ringover_configured:
        # S'assurer que le service a bien la clé active avant de tester
        ringover_service.set_api_key(ringover_key)
        test = await ringover_service.test_connection()
        ringover_connected = test.get("connected", False)

    return {
        "ringover": {
            "configured":      ringover_configured,
            "connected":       ringover_connected,
            "phone_number":    phone,
            "transfer_number": transfer,
            "api_url":         settings.RINGOVER_API_URL,
        },
        "openai": {
            "configured": openai_configured,
            "model":      openai_model,
            "tts_model":  settings.OPENAI_TTS_MODEL,
            "tts_voice":  tts_voice,
            "stt_model":  settings.OPENAI_STT_MODEL,
        },
        "agent": {
            "name":        agent_name,
            "company":     company,
            "language":    language,
            "temperature": temperature,
        },
        "app": {
            "name":    settings.APP_NAME,
            "debug":   settings.DEBUG,
            "version": "1.0.0",
        },
    }


@router.get("/status")
async def get_status(db: AsyncSession = Depends(get_db)):
    """Statut des intégrations. La BDD (config sauvegardée via l'UI) est
    prioritaire ; repli sur les variables d'environnement (.env)."""
    return await _build_status(db)


@router.post("/test-ringover")
async def test_ringover(db: AsyncSession = Depends(get_db)):
    # Utiliser la clé active (BDD > settings) avant le test
    key = await config_service.get_value(db, "ringover_api_key")
    if key:
        ringover_service.set_api_key(key)
    return await ringover_service.test_connection()


@router.get("/webhook-urls")
async def get_webhook_urls():
    """Retourne les URLs des webhooks à configurer dans Ringover"""
    base = f"http://{settings.APP_HOST}:{settings.APP_PORT}"
    return {
        "incoming": f"{base}/webhooks/ringover/incoming",
        "dtmf":     f"{base}/webhooks/ringover/dtmf",
        "speech":   f"{base}/webhooks/ringover/speech",
        "status":   f"{base}/webhooks/ringover/status",
        "hangup":   f"{base}/webhooks/ringover/hangup",
        "note":     "Remplacez l'adresse par votre IP publique ou URL ngrok en production",
    }
