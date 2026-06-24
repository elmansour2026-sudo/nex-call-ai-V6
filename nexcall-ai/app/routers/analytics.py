"""
NexCall AI v3 — Router Analytics
Statistiques globales des appels et resultats.
"""
import csv
import io
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.call import Call, CallStatus
from app.models.prospect import Prospect, ProspectStatus
from app.models.blacklist import Blacklist
from app.models.campaign import Campaign

router = APIRouter(prefix="/api/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)


@router.get("/campagne")
async def analytics_campagne(
    campaign_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Resultats de campagne : les 7 indicateurs metier demandes.
    Filtrable par campagne (sinon global)."""
    base = select(func.count(Prospect.id)).where(Prospect.is_archived == False)
    if campaign_id:
        base = base.where(Prospect.campaign_id == campaign_id)

    async def cnt(*statuses):
        q = base
        if statuses:
            q = q.where(Prospect.status.in_(list(statuses)))
        return await db.scalar(q) or 0

    total          = await cnt()
    # "Appeles" = tout contact qui a ete au moins contacte (statuts post-appel)
    appeles        = await cnt(
        ProspectStatus.APPELE.value, ProspectStatus.INTERESSE.value,
        ProspectStatus.PAS_INTERESSE.value, ProspectStatus.NE_REPOND_PAS.value,
        ProspectStatus.A_RAPPELER.value, ProspectStatus.TRANSFERE.value,
        ProspectStatus.REFUS_DEFINITIF.value, ProspectStatus.REACHED.value,
    )
    interesses     = await cnt(ProspectStatus.INTERESSE.value)
    sans_reponse   = await cnt(ProspectStatus.NE_REPOND_PAS.value)
    transferes     = await cnt(ProspectStatus.TRANSFERE.value)
    refuses        = await cnt(ProspectStatus.PAS_INTERESSE.value, ProspectStatus.REFUS_DEFINITIF.value)
    do_not_call    = await cnt(ProspectStatus.DO_NOT_CALL.value)
    a_rappeler     = await cnt(ProspectStatus.A_RAPPELER.value)
    nouveaux       = await cnt(ProspectStatus.NOUVEAU.value, ProspectStatus.EN_ATTENTE.value)

    taux_contact   = round(appeles / total * 100, 1) if total else 0
    taux_interet   = round(interesses / appeles * 100, 1) if appeles else 0

    return {
        "total_contacts": total,
        "appeles":        appeles,
        "interesses":     interesses,
        "sans_reponse":   sans_reponse,
        "transferes":     transferes,
        "refuses":        refuses,
        "do_not_call":    do_not_call,
        "a_rappeler":     a_rappeler,
        "nouveaux":       nouveaux,
        "taux_contact":   taux_contact,
        "taux_interet":   taux_interet,
    }


@router.get("/campagne/export")
async def export_campagne(
    campaign_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Export CSV des resultats de campagne (synthese par indicateur)."""
    stats = await analytics_campagne(campaign_id, db)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Indicateur", "Valeur"])
    rows = [
        ("Total contacts",          stats["total_contacts"]),
        ("Contacts appeles",        stats["appeles"]),
        ("Interesses",              stats["interesses"]),
        ("Sans reponse",            stats["sans_reponse"]),
        ("Transferes conseiller",   stats["transferes"]),
        ("Refuses",                 stats["refuses"]),
        ("Liste rouge (Do Not Call)", stats["do_not_call"]),
        ("A rappeler",              stats["a_rappeler"]),
        ("Nouveaux / en attente",   stats["nouveaux"]),
        ("Taux de contact (%)",     stats["taux_contact"]),
        ("Taux d'interet (%)",      stats["taux_interet"]),
    ]
    for label, val in rows:
        w.writerow([label, val])
    return PlainTextResponse(
        content=out.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=resultats_campagne.csv"},
    )


@router.get("/overview")
async def analytics_overview(db: AsyncSession = Depends(get_db)):
    # Appels
    total_calls = await db.scalar(select(func.count(Call.id))) or 0
    answered    = await db.scalar(select(func.count(Call.id)).where(
        Call.status.in_([CallStatus.COMPLETED.value, CallStatus.ANSWERED.value, CallStatus.TRANSFERRED.value]))) or 0
    no_answer   = await db.scalar(select(func.count(Call.id)).where(
        Call.status == CallStatus.MISSED.value)) or 0
    transfers   = await db.scalar(select(func.count(Call.id)).where(
        Call.status == CallStatus.TRANSFERRED.value)) or 0

    # Contacts par statut
    interested  = await db.scalar(select(func.count(Prospect.id)).where(
        Prospect.status == ProspectStatus.INTERESSE.value)) or 0
    refused     = await db.scalar(select(func.count(Prospect.id)).where(
        Prospect.status.in_([ProspectStatus.PAS_INTERESSE.value, ProspectStatus.REFUS_DEFINITIF.value]))) or 0
    blacklist   = await db.scalar(select(func.count(Blacklist.id))) or 0

    # Duree moyenne
    avg_dur = await db.scalar(select(func.avg(Call.duration)).where(
        Call.status == CallStatus.COMPLETED.value)) or 0

    answer_rate = round(answered / total_calls * 100, 1) if total_calls else 0
    transfer_rate = round(transfers / answered * 100, 1) if answered else 0

    return {
        "total_calls":   total_calls,
        "answered":      answered,
        "no_answer":     no_answer,
        "interested":    interested,
        "refused":       refused,
        "transfers":     transfers,
        "blacklist":     blacklist,
        "avg_duration":  round(avg_dur, 1),
        "answer_rate":   answer_rate,
        "transfer_rate": transfer_rate,
    }


@router.get("/by-status")
async def analytics_by_status(db: AsyncSession = Depends(get_db)):
    """Repartition des contacts par statut."""
    result = await db.execute(
        select(Prospect.status, func.count(Prospect.id))
        .where(Prospect.is_archived == False)
        .group_by(Prospect.status)
    )
    rows = result.all()
    labels = Prospect.STATUS_LABELS
    return [{"status": s, "label": labels.get(s, s), "count": c} for s, c in rows]


@router.get("/by-agent")
async def analytics_by_agent(db: AsyncSession = Depends(get_db)):
    """Performance par agent."""
    from app.models.agent import Agent
    agents_result = await db.execute(select(Agent))
    agents = agents_result.scalars().all()
    return [{
        "agent_id":   a.id,
        "name":       a.name,
        "service":    a.service_label,
        "total_calls": a.total_calls,
        "total_leads": a.total_leads,
        "conversion": a.conversion_rate,
    } for a in agents]
