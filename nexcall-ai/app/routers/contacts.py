"""
NexCall AI v3 — Router Contacts (clients/leads mutuelle)
Table principale, import enrichi, export, filtres, pagination.
"""
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Form
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.prospect import Prospect, ProspectStatus
from app.services.contact_service import contact_service
from app.services.blacklist_service import blacklist_service

router = APIRouter(prefix="/api/contacts", tags=["contacts"])
logger = logging.getLogger(__name__)


class ContactCreate(BaseModel):
    first_name:       Optional[str] = None
    last_name:        Optional[str] = None
    phone:            str
    birth_date:       Optional[str] = None
    resiliation_date: Optional[str] = None
    old_offer:        Optional[str] = None
    city:             Optional[str] = None
    extra_info:       Optional[str] = None
    notes:            Optional[str] = None
    campaign_id:      Optional[int] = None
    agent_id:         Optional[int] = None


class ContactUpdate(BaseModel):
    first_name:       Optional[str] = None
    last_name:        Optional[str] = None
    phone:            Optional[str] = None
    birth_date:       Optional[str] = None
    resiliation_date: Optional[str] = None
    old_offer:        Optional[str] = None
    city:             Optional[str] = None
    extra_info:       Optional[str] = None
    notes:            Optional[str] = None
    status:           Optional[str] = None
    campaign_id:      Optional[int] = None
    agent_id:         Optional[int] = None


@router.get("")
async def list_contacts(
    search:      Optional[str] = None,
    status:      Optional[str] = None,
    campaign_id: Optional[int] = None,
    agent_id:    Optional[int] = None,
    date_from:   Optional[str] = None,
    date_to:     Optional[str] = None,
    page:        int = Query(1, ge=1),
    per_page:    int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * per_page
    contacts, total = await contact_service.get_filtered(
        db, search=search, status=status, campaign_id=campaign_id,
        agent_id=agent_id, date_from=date_from, date_to=date_to,
        limit=per_page, offset=offset,
    )
    return {
        "contacts":  [c.to_dict() for c in contacts],
        "total":     total,
        "page":      page,
        "per_page":  per_page,
        "pages":     (total + per_page - 1) // per_page,
    }


@router.get("/stats")
async def contacts_stats(campaign_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    return await contact_service.get_stats(db, campaign_id)


@router.get("/export")
async def export_contacts(
    campaign_id: Optional[int] = None,
    status:      Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    csv_data = await contact_service.export_csv(db, campaign_id, status)
    return PlainTextResponse(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contacts_export.csv"},
    )


@router.post("/import")
async def import_contacts(
    campaign_id: Optional[int] = Form(None),
    agent_id:    Optional[int] = Form(None),
    delimiter:   str           = Form(","),
    file:        UploadFile     = File(...),
    db: AsyncSession = Depends(get_db),
):
    if not (file.filename.endswith(".csv") or file.filename.endswith(".txt")):
        raise HTTPException(400, "Format accepte : CSV. Pour Excel, exportez d'abord en CSV.")

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # gere le BOM Excel
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except Exception:
            raise HTTPException(400, "Encodage non supporte (UTF-8 ou Latin-1 requis)")

    result = await contact_service.import_csv(
        db, text, campaign_id=campaign_id, agent_id=agent_id, delimiter=delimiter
    )
    return result


class NumbersImport(BaseModel):
    numbers:     list[str]
    campaign_id: Optional[int] = None
    agent_id:    Optional[int] = None


@router.post("/import-numbers")
async def import_numbers(body: NumbersImport, db: AsyncSession = Depends(get_db)):
    """Import rapide : liste de numeros seuls (telephone obligatoire)."""
    if not body.numbers:
        raise HTTPException(400, "Aucun numero fourni")
    return await contact_service.import_numbers(
        db, body.numbers, campaign_id=body.campaign_id, agent_id=body.agent_id
    )


@router.get("/{contact_id}")
async def get_contact(contact_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Prospect).where(Prospect.id == contact_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Contact non trouve")
    return c.to_dict()


@router.post("", status_code=201)
async def create_contact(body: ContactCreate, db: AsyncSession = Depends(get_db)):
    phone = contact_service.normalize_phone(body.phone)
    if not contact_service.is_valid_phone(phone):
        raise HTTPException(400, "Numero de telephone invalide")
    if await blacklist_service.is_blacklisted(db, phone):
        raise HTTPException(400, "Ce numero est en liste noire (Do Not Call)")

    data = body.model_dump()
    data["phone"] = phone
    contact = Prospect(**data, status=ProspectStatus.NOUVEAU.value)
    db.add(contact)
    await db.flush()
    return contact.to_dict()


@router.put("/{contact_id}")
async def update_contact(contact_id: int, body: ContactUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Prospect).where(Prospect.id == contact_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Contact non trouve")

    data = body.model_dump(exclude_none=True)

    # Si on passe en do_not_call, ajouter a la blacklist
    if data.get("status") == ProspectStatus.DO_NOT_CALL.value:
        await blacklist_service.add(db, c.phone, reason="Statut do_not_call", source="manual")

    for field, value in data.items():
        setattr(c, field, value)
    c.updated_at = datetime.utcnow()
    await db.flush()
    return c.to_dict()


@router.delete("/{contact_id}")
async def delete_contact(contact_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Prospect).where(Prospect.id == contact_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Contact non trouve")
    await db.delete(c)
    return {"success": True}


@router.post("/{contact_id}/blacklist")
async def blacklist_contact(contact_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Prospect).where(Prospect.id == contact_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Contact non trouve")
    await blacklist_service.add(db, c.phone, reason="Ajout manuel", source="manual")
    c.status = ProspectStatus.DO_NOT_CALL.value
    c.updated_at = datetime.utcnow()
    return {"success": True, "message": "Contact ajoute a la liste noire"}
