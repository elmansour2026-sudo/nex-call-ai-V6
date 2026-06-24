"""
NexCall AI v3 — Router Blacklist (Do Not Call)
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.blacklist_service import blacklist_service

router = APIRouter(prefix="/api/blacklist", tags=["blacklist"])
logger = logging.getLogger(__name__)


class BlacklistCreate(BaseModel):
    phone:  str
    reason: Optional[str] = None
    notes:  Optional[str] = None


@router.get("")
async def list_blacklist(
    limit:  int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    entries = await blacklist_service.get_all(db, limit, offset)
    total = await blacklist_service.count(db)
    return {"entries": [e.to_dict() for e in entries], "total": total}


@router.post("", status_code=201)
async def add_blacklist(body: BlacklistCreate, db: AsyncSession = Depends(get_db)):
    entry = await blacklist_service.add(
        db, body.phone, reason=body.reason or "Ajout manuel",
        source="manual", notes=body.notes,
    )
    if not entry:
        raise HTTPException(400, "Numero invalide ou deja en liste noire")
    return entry.to_dict()


@router.delete("/{phone}")
async def remove_blacklist(phone: str, db: AsyncSession = Depends(get_db)):
    ok = await blacklist_service.remove(db, phone)
    if not ok:
        raise HTTPException(404, "Numero non trouve en liste noire")
    return {"success": True}


@router.get("/check/{phone}")
async def check_blacklist(phone: str, db: AsyncSession = Depends(get_db)):
    blocked = await blacklist_service.is_blacklisted(db, phone)
    return {"phone": phone, "blacklisted": blocked}
