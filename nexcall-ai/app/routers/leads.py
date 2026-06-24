"""
NexCall AI — Router Leads
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.lead import Lead
from app.services.lead_service import lead_service

router = APIRouter(prefix="/api/leads", tags=["leads"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class LeadCreate(BaseModel):
    phone:      str
    first_name: Optional[str] = None
    last_name:  Optional[str] = None
    email:      Optional[str] = None
    interest:   Optional[str] = None
    score:      float = 0.0
    budget:     Optional[str] = None
    urgency:    Optional[str] = None
    notes:      Optional[str] = None
    source:     str = "manual"


class LeadUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name:  Optional[str] = None
    email:      Optional[str] = None
    interest:   Optional[str] = None
    score:      Optional[float] = None
    status:     Optional[str] = None
    budget:     Optional[str] = None
    urgency:    Optional[str] = None
    notes:      Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("")
async def list_leads(
    limit:    int           = Query(100, ge=1, le=500),
    offset:   int           = Query(0, ge=0),
    status:   Optional[str] = None,
    interest: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    leads = await lead_service.get_all(db, limit, offset, status, interest)
    return [l.to_dict() for l in leads]


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    return await lead_service.get_stats(db)


@router.get("/{lead_id}")
async def get_lead(lead_id: int, db: AsyncSession = Depends(get_db)):
    lead = await lead_service.get_by_id(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead non trouvé")
    return lead.to_dict()


@router.post("", status_code=201)
async def create_lead(body: LeadCreate, db: AsyncSession = Depends(get_db)):
    lead = Lead(
        phone      = body.phone,
        first_name = body.first_name,
        last_name  = body.last_name,
        email      = body.email,
        interest   = body.interest,
        score      = body.score,
        budget     = body.budget,
        urgency    = body.urgency,
        notes      = body.notes,
        source     = body.source,
    )
    lead.recalculate_status()
    db.add(lead)
    await db.flush()
    return lead.to_dict()


@router.put("/{lead_id}")
async def update_lead(lead_id: int, body: LeadUpdate, db: AsyncSession = Depends(get_db)):
    lead = await lead_service.get_by_id(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead non trouvé")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(lead, field, value)

    # Recalcule le statut si le score a changé
    if body.score is not None and body.status is None:
        lead.recalculate_status()

    lead.updated_at = datetime.utcnow()
    await db.flush()
    return lead.to_dict()


@router.delete("/{lead_id}")
async def delete_lead(lead_id: int, db: AsyncSession = Depends(get_db)):
    ok = await lead_service.delete(db, lead_id)
    if not ok:
        raise HTTPException(404, "Lead non trouvé")
    return {"success": True}


@router.post("/{lead_id}/archive")
async def archive_lead(lead_id: int, db: AsyncSession = Depends(get_db)):
    lead = await lead_service.get_by_id(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead non trouvé")
    lead.is_archived = True
    lead.updated_at = datetime.utcnow()
    return {"success": True}
