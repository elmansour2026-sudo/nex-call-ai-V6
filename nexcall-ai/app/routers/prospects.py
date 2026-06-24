"""
NexCall AI v2 — Router Prospects + Import CSV + Campagnes Outbound
"""
import logging
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Query, Form
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.prospect import Prospect, ProspectStatus
from app.models.campaign import Campaign, CampaignStatus
from app.models.agent import Agent
from app.services.outbound_service import outbound_service

router = APIRouter(prefix="/api/prospects", tags=["prospects"])
logger = logging.getLogger(__name__)


@router.get("")
async def list_prospects(
    campaign_id: Optional[int] = None,
    status:      Optional[str] = None,
    limit:  int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    q = select(Prospect).where(Prospect.is_archived == False)
    if campaign_id:
        q = q.where(Prospect.campaign_id == campaign_id)
    if status:
        q = q.where(Prospect.status == status)
    q = q.order_by(Prospect.id).limit(limit).offset(offset)
    result = await db.execute(q)
    return [p.to_dict() for p in result.scalars().all()]


@router.get("/stats")
async def get_stats(campaign_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    q_base = select(func.count(Prospect.id))
    if campaign_id:
        q_base = q_base.where(Prospect.campaign_id == campaign_id)

    total     = await db.scalar(q_base.where(Prospect.is_archived == False)) or 0
    pending   = await db.scalar(q_base.where(Prospect.status == "pending", Prospect.is_archived == False)) or 0
    reached   = await db.scalar(q_base.where(Prospect.status == "reached", Prospect.is_archived == False)) or 0
    converted = await db.scalar(q_base.where(Prospect.status == "converted", Prospect.is_archived == False)) or 0
    callback  = await db.scalar(q_base.where(Prospect.status == "callback", Prospect.is_archived == False)) or 0

    return {
        "total": total, "pending": pending, "reached": reached,
        "converted": converted, "callback": callback,
        "progress_pct": round((total - pending) / total * 100, 1) if total > 0 else 0,
    }


@router.post("/import-csv")
async def import_csv(
    campaign_id: int       = Form(...),
    delimiter:   str       = Form(","),
    file:        UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Importe un fichier CSV de prospects pour une campagne."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Le fichier doit etre au format CSV")

    content = await file.read()
    try:
        csv_text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            csv_text = content.decode("latin-1")
        except Exception:
            raise HTTPException(400, "Encodage du fichier non supporte (utilisez UTF-8 ou Latin-1)")

    result = await outbound_service.import_csv(db, campaign_id, csv_text, delimiter)
    return result


@router.post("/import-manual")
async def import_manual(
    campaign_id: int,
    prospects:   list[dict],
    db: AsyncSession = Depends(get_db),
):
    """Import manuel d'une liste de prospects (JSON)."""
    imported = 0
    for p in prospects:
        phone = p.get("phone") or p.get("telephone", "")
        if not phone:
            continue
        prospect = Prospect(
            campaign_id = campaign_id,
            phone       = phone,
            first_name  = p.get("first_name") or p.get("prenom"),
            last_name   = p.get("last_name") or p.get("nom"),
            email       = p.get("email"),
            city        = p.get("city") or p.get("ville"),
            extra_info  = p.get("extra_info") or p.get("info"),
            status      = ProspectStatus.PENDING.value,
        )
        db.add(prospect)
        imported += 1
    await db.flush()
    return {"imported": imported}


@router.post("/{prospect_id}/call")
async def call_prospect(prospect_id: int, db: AsyncSession = Depends(get_db)):
    """Declenche un appel vers ce prospect maintenant."""
    from app.services.ringover_service import ringover_service

    result = await db.execute(select(Prospect).where(Prospect.id == prospect_id))
    prospect = result.scalar_one_or_none()
    if not prospect:
        raise HTTPException(404, "Prospect non trouve")

    # Recuperer la campagne, puis l'agent explicitement (evite le lazy-load
    # relationnel async non supporte par SQLAlchemy sans selectinload).
    camp_result = await db.execute(select(Campaign).where(Campaign.id == prospect.campaign_id))
    campaign = camp_result.scalar_one_or_none()
    if not campaign or not campaign.agent_id:
        raise HTTPException(400, "Campagne ou agent non configure")

    agent_result = await db.execute(select(Agent).where(Agent.id == campaign.agent_id))
    agent = agent_result.scalar_one_or_none()
    if not agent:
        raise HTTPException(400, "Agent non trouve")

    from app.services.outbound_service import outbound_service
    from_number = await outbound_service._resolve_caller_number(db, agent)
    if not from_number:
        raise HTTPException(400, "Aucun numero appelant configure (RINGOVER_PHONE_NUMBER manquant)")

    res = await ringover_service.make_outbound_call(from_number, prospect.phone)
    if res.get("success"):
        prospect.status = ProspectStatus.CALLING.value
        prospect.last_attempt_at = datetime.utcnow()
        prospect.attempt_count += 1
        return {"success": True, "message": f"Appel lance vers {prospect.phone}"}
    else:
        raise HTTPException(502, f"Erreur Ringover: {res.get('error')}")


@router.delete("/{prospect_id}")
async def delete_prospect(prospect_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Prospect).where(Prospect.id == prospect_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Prospect non trouve")
    await db.delete(p)
    return {"success": True}
