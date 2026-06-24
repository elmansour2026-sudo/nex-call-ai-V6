"""
NexCall AI v3 — Router Scripts (Script Builder)
"""
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.call_script import CallScript

router = APIRouter(prefix="/api/scripts", tags=["scripts"])
logger = logging.getLogger(__name__)


class ScriptCreate(BaseModel):
    name:          str
    agent_id:      Optional[int] = None
    introduction:  Optional[str] = None
    qualification: Optional[str] = None
    objections:    Optional[str] = None
    offer_pitch:   Optional[str] = None
    closing:       Optional[str] = None


class ScriptUpdate(BaseModel):
    name:          Optional[str] = None
    agent_id:      Optional[int] = None
    introduction:  Optional[str] = None
    qualification: Optional[str] = None
    objections:    Optional[str] = None
    offer_pitch:   Optional[str] = None
    closing:       Optional[str] = None
    is_active:     Optional[bool] = None


@router.get("")
async def list_scripts(agent_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    q = select(CallScript)
    if agent_id:
        q = q.where(CallScript.agent_id == agent_id)
    q = q.order_by(CallScript.created_at.desc())
    result = await db.execute(q)
    return [s.to_dict() for s in result.scalars().all()]


@router.get("/{script_id}")
async def get_script(script_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CallScript).where(CallScript.id == script_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Script non trouve")
    return s.to_dict()


@router.post("", status_code=201)
async def create_script(body: ScriptCreate, db: AsyncSession = Depends(get_db)):
    script = CallScript(**body.model_dump())
    db.add(script)
    await db.flush()
    return script.to_dict()


@router.put("/{script_id}")
async def update_script(script_id: int, body: ScriptUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CallScript).where(CallScript.id == script_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Script non trouve")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(s, field, value)
    s.updated_at = datetime.utcnow()
    return s.to_dict()


@router.delete("/{script_id}")
async def delete_script(script_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CallScript).where(CallScript.id == script_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Script non trouve")
    await db.delete(s)
    return {"success": True}


@router.post("/{script_id}/preview")
async def preview_script(script_id: int, variables: dict, db: AsyncSession = Depends(get_db)):
    """Rend le script avec des variables d'exemple."""
    result = await db.execute(select(CallScript).where(CallScript.id == script_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Script non trouve")
    return s.render(variables)
