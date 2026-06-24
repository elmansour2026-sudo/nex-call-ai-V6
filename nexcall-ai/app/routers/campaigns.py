"""
NexCall AI v2 — Router Campagnes (mis a jour)
"""
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.campaign import Campaign, CampaignStatus
from app.services.outbound_service import outbound_service

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])
logger = logging.getLogger(__name__)


def _parse_dt(value):
    """Convertit une chaine ISO en datetime. Renvoie None si vide/invalide.
    Tolere le 'Z' final et les espaces."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except Exception:
        return None


def _is_future(dt) -> bool:
    """True si la date est dans le futur (campagne a programmer)."""
    if not isinstance(dt, datetime):
        return False
    now = datetime.utcnow()
    # tolerance d'une minute : en-deca, on considere "maintenant"
    return (dt - now).total_seconds() > 60


class CampaignCreate(BaseModel):
    name:            str
    description:     Optional[str] = None
    type:            str = "outbound"
    agent_id:        Optional[int] = None
    scheduled_at:    Optional[str] = None
    launch_now:      bool = False
    test_phone_number: Optional[str] = None
    max_concurrent:  int = 3
    call_hours_start: Optional[str] = None
    call_hours_end:  Optional[str] = None
    transfer_number: Optional[str] = None
    max_attempts:    int = 3
    ring_timeout:    int = 45
    target_interest: Optional[str] = None
    target_region:   Optional[str] = None
    ai_system_prompt:Optional[str] = None
    ivr_message:     Optional[str] = None


class CampaignUpdate(BaseModel):
    name:            Optional[str] = None
    description:     Optional[str] = None
    type:            Optional[str] = None
    status:          Optional[str] = None
    agent_id:        Optional[int] = None
    max_concurrent:  Optional[int] = None
    scheduled_at:    Optional[str] = None
    test_phone_number: Optional[str] = None
    call_hours_start: Optional[str] = None
    call_hours_end:  Optional[str] = None
    transfer_number: Optional[str] = None
    max_attempts:    Optional[int] = None
    ring_timeout:    Optional[int] = None
    target_interest: Optional[str] = None
    ai_system_prompt:Optional[str] = None
    ivr_message:     Optional[str] = None


@router.get("")
async def list_campaigns(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).order_by(Campaign.created_at.desc()))
    return [c.to_dict() for c in result.scalars().all()]


@router.post("", status_code=201)
async def create_campaign(body: CampaignCreate, db: AsyncSession = Depends(get_db)):
    scheduled = _parse_dt(body.scheduled_at)
    # Si "lancer maintenant" est demande, ou si la date est immediate, pas de programmation
    if body.launch_now or not _is_future(scheduled):
        scheduled = None
        status = CampaignStatus.DRAFT.value
    else:
        status = CampaignStatus.SCHEDULED.value

    campaign = Campaign(
        name=body.name, description=body.description, type=body.type,
        agent_id=body.agent_id, scheduled_at=scheduled,
        test_phone_number=body.test_phone_number,
        max_concurrent=body.max_concurrent,
        call_hours_start=body.call_hours_start, call_hours_end=body.call_hours_end,
        transfer_number=body.transfer_number, max_attempts=body.max_attempts,
        ring_timeout=body.ring_timeout,
        target_interest=body.target_interest, target_region=body.target_region,
        ai_system_prompt=body.ai_system_prompt, ivr_message=body.ivr_message,
        status=status,
    )
    db.add(campaign)
    await db.flush()
    return campaign.to_dict()


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Campagne non trouvee")
    return c.to_dict()


@router.put("/{campaign_id}")
async def update_campaign(campaign_id: int, body: CampaignUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Campagne non trouvee")
    data = body.model_dump(exclude_none=True)
    # Convertir scheduled_at (chaine ISO) en datetime avant l'enregistrement
    if "scheduled_at" in data:
        data["scheduled_at"] = _parse_dt(data["scheduled_at"])
    for field, value in data.items():
        setattr(c, field, value)
    c.updated_at = datetime.utcnow()
    return c.to_dict()


@router.post("/{campaign_id}/activate")
async def activate(campaign_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Campagne non trouvee")
    c.status = CampaignStatus.ACTIVE.value
    c.is_active = True
    c.started_at = c.started_at or datetime.utcnow()
    return {"success": True, "status": c.status}


@router.post("/{campaign_id}/launch")
async def launch_outbound(campaign_id: int, db: AsyncSession = Depends(get_db)):
    """Lance effectivement les appels sortants."""
    return await outbound_service.launch_campaign(db, campaign_id)


class TestCallBody(BaseModel):
    test_phone_number: Optional[str] = None


@router.post("/{campaign_id}/test-call")
async def test_call(campaign_id: int, body: TestCallBody = None, db: AsyncSession = Depends(get_db)):
    """Mode TEST : lance un VRAI appel Ringover vers le numero de test, avec
    l'agent IA de la campagne. Aucune simulation. Succes uniquement si Ringover
    confirme l'appel ; sinon l'erreur exacte est renvoyee."""
    phone = body.test_phone_number if body else None
    result = await outbound_service.launch_test_call(db, campaign_id, test_phone=phone)
    if not result.get("success"):
        # 400 seulement pour une erreur de saisie (numero manquant) ;
        # les echecs techniques restent en 200 avec le detail de l'erreur.
        if "numero de test" in (result.get("error") or "").lower():
            raise HTTPException(400, result["error"])
    return result


@router.post("/{campaign_id}/pause")
async def pause(campaign_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Campagne non trouvee")
    c.status = CampaignStatus.PAUSED.value
    c.is_active = False
    return {"success": True, "status": c.status}


@router.post("/{campaign_id}/complete")
async def complete(campaign_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Campagne non trouvee")
    c.status = CampaignStatus.COMPLETED.value
    c.is_active = False
    c.ended_at = datetime.utcnow()
    return {"success": True, "status": c.status}


@router.get("/{campaign_id}/stats")
async def campaign_stats(campaign_id: int, db: AsyncSession = Depends(get_db)):
    return await outbound_service.get_campaign_stats(db, campaign_id)


@router.delete("/{campaign_id}")
async def delete_campaign(campaign_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Campagne non trouvee")
    await db.delete(c)
    return {"success": True}
