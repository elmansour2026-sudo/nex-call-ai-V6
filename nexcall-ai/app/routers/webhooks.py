"""
NexCall AI v2 — Webhooks Ringover (multi-agents)
Gere les appels entrants ET sortants, avec agent specifique par campagne/prospect.
"""
import json
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.call import Call, CallStatus
from app.models.agent import Agent
from app.models.prospect import Prospect, ProspectStatus
from app.models.campaign import Campaign
from app.services.ai_agent import ai_agent
from app.services.ivr_service import ivr_service
from app.services.lead_service import lead_service
from app.services.ringover_service import ringover_service
from app.services.outbound_service import outbound_service
from app.services.blacklist_service import blacklist_service
from app.config import settings

router = APIRouter(prefix="/webhooks/ringover", tags=["webhooks"])
logger = logging.getLogger(__name__)

# ── Detection deterministe (independante du LLM) ──────────────────────────
_DO_NOT_CALL_PHRASES = [
    "ne m'appelez plus", "ne m appelez plus", "arretez de m'appeler",
    "arretez de m appeler", "retirez mon numero", "rayez mon numero",
    "plus jamais", "ne me rappelez plus", "liste rouge", "stop",
]
_HUMAN_TRANSFER_PHRASES = [
    "parler a quelqu'un", "parler a quelqu un", "un conseiller",
    "une personne", "un humain", "un agent", "quelqu'un de reel",
    "une vraie personne", "parler a un conseiller",
]

def _normalize_text(text: str) -> str:
    return (text or "").lower().strip()

def _detect_do_not_call(text: str) -> bool:
    t = _normalize_text(text)
    return any(p in t for p in _DO_NOT_CALL_PHRASES)

def _detect_human_transfer(text: str) -> bool:
    t = _normalize_text(text)
    return any(p in t for p in _HUMAN_TRANSFER_PHRASES)


def _map_ringover_status(raw: str) -> str:
    return {
        "ringing": CallStatus.RINGING.value, "answered": CallStatus.ANSWERED.value,
        "in_progress": CallStatus.IN_PROGRESS.value, "transferred": CallStatus.TRANSFERRED.value,
        "ended": CallStatus.COMPLETED.value, "completed": CallStatus.COMPLETED.value,
        "hangup": CallStatus.COMPLETED.value, "no_answer": CallStatus.MISSED.value,
        "busy": CallStatus.MISSED.value, "failed": CallStatus.FAILED.value,
    }.get(raw.lower(), raw)


async def _get_or_create_call(db: AsyncSession, call_id: str, caller: str, called: str = "",
                               direction: str = "inbound", agent_id: Optional[int] = None,
                               prospect_id: Optional[int] = None, campaign_id: Optional[int] = None) -> Call:
    result = await db.execute(select(Call).where(Call.ringover_call_id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        call = Call(
            ringover_call_id=call_id, caller_number=caller,
            called_number=called or settings.RINGOVER_PHONE_NUMBER or "",
            status=CallStatus.INCOMING.value, direction=direction,
            agent_id=agent_id, prospect_id=prospect_id, campaign_id=campaign_id,
            started_at=datetime.utcnow(),
        )
        db.add(call)
        await db.flush()
    return call


async def _find_prospect_by_phone(db: AsyncSession, phone: str) -> Optional[Prospect]:
    """Trouve un prospect en cours d'appel correspondant a ce numero."""
    result = await db.execute(
        select(Prospect).where(Prospect.phone == phone, Prospect.status == ProspectStatus.CALLING.value)
        .order_by(Prospect.last_attempt_at.desc())
    )
    return result.scalar_one_or_none()


# ──────────────────────────────────────────────────────────────────────────
# 1. Appel entrant (inbound classique)
# ──────────────────────────────────────────────────────────────────────────
@router.post("/incoming")
async def webhook_incoming(request: Request, db: AsyncSession = Depends(get_db)):
    body: dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass

    call_id = body.get("call_uuid") or body.get("call_id") or f"rng_{int(datetime.utcnow().timestamp()*1000)}"
    caller  = body.get("from_number") or body.get("caller") or body.get("from", "Inconnu")
    called  = body.get("to_number")   or body.get("callee") or ""

    logger.info(f"[WEBHOOK] Incoming: {caller} -> {called} (id={call_id})")

    # Trouver l'agent assigne a ce numero appele
    agent = None
    if called:
        result = await db.execute(select(Agent).where(Agent.ringover_number == called, Agent.is_active == True))
        agent = result.scalar_one_or_none()

    call = await _get_or_create_call(db, call_id, caller, called, "inbound", agent_id=agent.id if agent else None)

    ai_agent.create_session(call_id, agent=agent)
    greeting = (agent.script_intro if agent and agent.script_intro else ivr_service.get_greeting())

    return {"status": "ok", "call_id": call_id, "action": "play_ivr", "message": greeting}


# ──────────────────────────────────────────────────────────────────────────
# 1b. Appel sortant connecte (outbound - prospect repond)
# ──────────────────────────────────────────────────────────────────────────
@router.post("/outbound-answered")
async def webhook_outbound_answered(request: Request, db: AsyncSession = Depends(get_db)):
    """Declenche quand un prospect repond a un appel sortant."""
    body: dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass

    call_id = body.get("call_uuid") or body.get("call_id", "")
    to_number = body.get("to_number") or body.get("to", "")

    logger.info(f"[WEBHOOK] Outbound answered: call={call_id} to={to_number}")

    prospect = await _find_prospect_by_phone(db, to_number)
    agent = None
    campaign = None
    if prospect:
        result = await db.execute(select(Campaign).where(Campaign.id == prospect.campaign_id))
        campaign = result.scalar_one_or_none()
        if campaign and campaign.agent_id:
            result2 = await db.execute(select(Agent).where(Agent.id == campaign.agent_id))
            agent = result2.scalar_one_or_none()
        prospect.status = ProspectStatus.REACHED.value

    call = await _get_or_create_call(
        db, call_id, caller=settings.RINGOVER_PHONE_NUMBER or "system", called=to_number,
        direction="outbound", agent_id=agent.id if agent else None,
        prospect_id=prospect.id if prospect else None,
        campaign_id=campaign.id if campaign else None,
    )
    call.status = CallStatus.ANSWERED.value
    call.answered_at = datetime.utcnow()

    prospect_name = prospect.full_name if prospect else "Madame/Monsieur"
    session = ai_agent.create_session(call_id, agent=agent, prospect_name=prospect_name)

    intro = ""
    if agent and agent.script_intro:
        intro = agent.script_intro.format(
            agent_name=agent.name, prospect_name=prospect_name,
            company_name=settings.AI_COMPANY_NAME,
        )
    else:
        intro = f"Bonjour {prospect_name}, je suis un assistant IA de {settings.AI_COMPANY_NAME}. Avez-vous un instant ?"

    await db.flush()
    return {"status": "ok", "action": "speak", "message": intro, "voice": agent.voice if agent else "nova"}


# ──────────────────────────────────────────────────────────────────────────
# 2. Touche DTMF
# ──────────────────────────────────────────────────────────────────────────
@router.post("/dtmf")
async def webhook_dtmf(request: Request, db: AsyncSession = Depends(get_db)):
    body: dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass

    call_id = body.get("call_uuid") or body.get("call_id", "")
    digit   = str(body.get("digit") or body.get("dtmf", ""))

    logger.info(f"[WEBHOOK] DTMF: call={call_id} digit={digit}")
    ivr_result = ivr_service.process_dtmf(digit)

    if call_id:
        result = await db.execute(select(Call).where(Call.ringover_call_id == call_id))
        call = result.scalar_one_or_none()
        if call:
            call.ivr_choice = ivr_result.get("intent")
            call.status = CallStatus.IN_PROGRESS.value
            call.answered_at = call.answered_at or datetime.utcnow()
            await db.flush()

    session = ai_agent.get_session(call_id)
    if session:
        session.ivr_choice = ivr_result.get("intent")

    if ivr_result.get("is_transfer"):
        transfer_number = settings.RINGOVER_TRANSFER_NUMBER
        if session and session.agent and session.agent.transfer_number:
            transfer_number = session.agent.transfer_number
        if transfer_number and call_id:
            await ringover_service.transfer_call(call_id, transfer_number)
        return {"status": "ok", "action": "transfer", "to": transfer_number, "message": ivr_result["message"]}

    return {"status": "ok", "action": "connect_ai" if ivr_result["valid"] else "replay_ivr",
            "intent": ivr_result.get("intent"), "message": ivr_result["message"]}


# ──────────────────────────────────────────────────────────────────────────
# 3. Parole — coeur du systeme multi-agents
# ──────────────────────────────────────────────────────────────────────────
@router.post("/speech")
async def webhook_speech(request: Request, db: AsyncSession = Depends(get_db)):
    body: dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass

    call_id    = body.get("call_uuid") or body.get("call_id", "")
    transcript = body.get("transcript") or body.get("text", "")

    logger.info(f"[WEBHOOK] Speech: call={call_id} text='{transcript[:80]}'")

    session = ai_agent.get_session(call_id)
    agent = session.agent if session else None
    ivr_choice = session.ivr_choice if session else None
    prospect_name = session.prospect_name if session else ""

    ai_response = await ai_agent.chat(
        call_id=call_id, user_message=transcript, agent=agent,
        ivr_choice=ivr_choice, prospect_name=prospect_name,
    )

    response_text = ai_response["text"]
    lead_data = ai_response.get("lead_data")
    qualification = ai_response.get("qualification")

    call = None
    if call_id:
        result = await db.execute(select(Call).where(Call.ringover_call_id == call_id))
        call = result.scalar_one_or_none()
        if call:
            existing = call.transcript or ""
            call.transcript = f"{existing}\nClient : {transcript}\nIA : {response_text}".strip()

            # Sauvegarde lead (v1 compat)
            if lead_data and call.caller_number:
                try:
                    lead = await lead_service.upsert_from_call(db, call.caller_number, lead_data)
                    call.lead_id = lead.id
                except Exception as e:
                    logger.error(f"Lead upsert error: {e}")

            # Sauvegarde qualification (v2) si suffisamment de donnees
            # NOTE: on utilise la variable `agent` (deja chargee en memoire depuis
            # la session de conversation) plutot que `call.agent` qui declencherait
            # un lazy-load relationnel non supporte en mode async sans selectinload.
            if qualification and qualification.get("intent"):
                lead_id = call.lead_id
                agent_service_name = agent.service if agent else None

                # Creer un lead aussi depuis la qualification si pas deja fait
                if not lead_id and qualification.get("lead_score", 0) > 0:
                    qual_as_lead = {
                        "first_name": qualification.get("prospect_name", "").split(" ")[0] if qualification.get("prospect_name") else None,
                        "interest":   agent_service_name,
                        "score":      qualification.get("lead_score", 0),
                        "budget":     qualification.get("budget"),
                        "urgency":    qualification.get("urgency"),
                        "notes":      qualification.get("need_summary"),
                    }
                    try:
                        lead = await lead_service.upsert_from_call(db, call.caller_number, qual_as_lead)
                        call.lead_id = lead.id
                        lead_id = lead.id
                    except Exception as e:
                        logger.error(f"Qualification->Lead error: {e}")

                try:
                    await outbound_service.create_qualification(
                        db, call_id=call.id, agent_id=call.agent_id,
                        prospect_id=call.prospect_id, lead_id=lead_id,
                        qual_data={
                            "intent":        qualification.get("intent"),
                            "lead_score":    qualification.get("lead_score", 0),
                            "prospect_name": qualification.get("prospect_name"),
                            "service":       agent_service_name,
                            "need_summary":  qualification.get("need_summary"),
                            "budget":        qualification.get("budget"),
                            "urgency":       qualification.get("urgency"),
                            "action":        qualification.get("action"),
                        },
                    )
                except Exception as e:
                    logger.error(f"Qualification save error: {e}")

            await db.flush()

    # ── Detection deterministe (priorite sur le LLM) ──────────────────────
    # Ces deux signaux sont critiques et ne doivent pas dependre du modele.
    wants_human = _detect_human_transfer(transcript) or _detect_human_transfer(response_text)
    says_dnc    = _detect_do_not_call(transcript)
    qual_intent = (qualification or {}).get("intent")
    qual_action = (qualification or {}).get("action")

    # 1) "Ne m'appelez plus" -> blacklist + statut do_not_call
    if says_dnc or qual_intent == "do_not_call" or qual_action == "do_not_call":
        if call and call.caller_number:
            try:
                await blacklist_service.add(
                    db, call.caller_number,
                    reason="Demande du client pendant l'appel", source="call",
                )
            except Exception as e:
                logger.error(f"Blacklist add error: {e}")
            # Mettre a jour le prospect lie
            if call.prospect_id:
                pr = await db.execute(select(Prospect).where(Prospect.id == call.prospect_id))
                prospect = pr.scalar_one_or_none()
                if prospect:
                    prospect.status = ProspectStatus.DO_NOT_CALL.value
                    prospect.updated_at = datetime.utcnow()
            await db.flush()
        return {
            "status": "ok", "action": "speak",
            "message": response_text or "Tres bien, je note votre demande. Je vous retire de notre liste. Bonne journee.",
            "voice": agent.voice if agent else "nova",
            "should_transfer": False, "transfer_to": None, "do_not_call": True,
        }

    # Decision de transfert (seuil de l'agent + detection humain + LLM)
    threshold = agent.transfer_score if agent else settings.LEAD_SCORE_THRESHOLD
    score = (qualification or {}).get("lead_score") or (lead_data or {}).get("score") or 0
    should_transfer = bool(
        wants_human
        or qual_action == "transfer_agent"
        or (qualification and qualification.get("should_transfer"))
        or score >= threshold
    )

    transfer_to = None
    if should_transfer:
        transfer_to = (agent.transfer_number if agent else None) or settings.RINGOVER_TRANSFER_NUMBER
        # Mettre a jour le prospect en "transfere_conseiller"
        if call and call.prospect_id:
            pr = await db.execute(select(Prospect).where(Prospect.id == call.prospect_id))
            prospect = pr.scalar_one_or_none()
            if prospect:
                prospect.status = ProspectStatus.TRANSFERE.value
                prospect.updated_at = datetime.utcnow()
            await db.flush()
        # Effectuer le transfert Ringover
        if transfer_to and call_id:
            try:
                await ringover_service.transfer_call(call_id, transfer_to)
            except Exception as e:
                logger.error(f"Transfer error: {e}")

    return {
        "status": "ok",
        "action": "transfer_then_speak" if should_transfer else "speak",
        "message": response_text,
        "voice": agent.voice if agent else "nova",
        "should_transfer": should_transfer,
        "transfer_to": transfer_to,
    }


# ──────────────────────────────────────────────────────────────────────────
# 4. Statut
# ──────────────────────────────────────────────────────────────────────────
@router.post("/status")
async def webhook_status(request: Request, db: AsyncSession = Depends(get_db)):
    body: dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass

    call_id  = body.get("call_uuid") or body.get("call_id", "")
    status   = body.get("status", "")
    duration = body.get("duration") or body.get("call_duration", 0)

    logger.info(f"[WEBHOOK] Status: call={call_id} status={status} duration={duration}s")
    if not call_id:
        return {"status": "ok", "ignored": True}

    result = await db.execute(select(Call).where(Call.ringover_call_id == call_id))
    call = result.scalar_one_or_none()

    if call:
        call.status = _map_ringover_status(status)
        if duration:
            call.duration = int(duration)

        if status.lower() in ("ended", "completed", "hangup"):
            call.ended_at = datetime.utcnow()
            if not call.duration and call.started_at:
                call.duration = int((datetime.utcnow() - call.started_at).total_seconds())

            # Charger explicitement l'agent (evite le lazy-load async non supporte)
            agent = None
            if call.agent_id:
                agent_result = await db.execute(select(Agent).where(Agent.id == call.agent_id))
                agent = agent_result.scalar_one_or_none()

            agent_name = agent.name if agent else "Agent IA"
            if call.transcript:
                try:
                    call.ai_summary = await ai_agent.summarize_call(call.transcript, agent_name=agent_name)
                except Exception as e:
                    logger.warning(f"Summary error: {e}")

            # Mise a jour metriques agent (reutilise l'objet deja charge ci-dessus)
            if agent:
                agent.total_calls += 1
                if call.lead_id:
                    agent.total_leads += 1
                if call.status == CallStatus.TRANSFERRED.value:
                    agent.total_transfers += 1

            # Mise a jour campagne
            if call.campaign_id:
                camp_result = await db.execute(select(Campaign).where(Campaign.id == call.campaign_id))
                campaign = camp_result.scalar_one_or_none()
                if campaign:
                    campaign.total_calls += 1
                    if call.status == CallStatus.COMPLETED.value:
                        campaign.answered_calls += 1
                    elif call.status == CallStatus.MISSED.value:
                        campaign.missed_calls += 1
                    if call.lead_id:
                        campaign.leads_generated += 1
                    if campaign.total_calls > 0:
                        campaign.conversion_rate = round(campaign.leads_generated / campaign.total_calls * 100, 1)

            # Mise a jour du prospect (retry system + statut final)
            if call.prospect_id:
                pr = await db.execute(select(Prospect).where(Prospect.id == call.prospect_id))
                prospect = pr.scalar_one_or_none()
                if prospect:
                    prospect.last_call_at = datetime.utcnow()
                    # Ne pas ecraser un statut terminal (do_not_call, transfere, refus...)
                    from app.models.prospect import TERMINAL_STATUSES
                    if prospect.status not in TERMINAL_STATUSES:
                        if call.status == CallStatus.MISSED.value:
                            # Pas de reponse -> retry: statut ne_repond_pas
                            prospect.status = ProspectStatus.NE_REPOND_PAS.value
                        elif call.status == CallStatus.TRANSFERRED.value:
                            prospect.status = ProspectStatus.TRANSFERE.value
                        elif call.status == CallStatus.COMPLETED.value:
                            # Joint et conversation terminee
                            if prospect.status in (ProspectStatus.NOUVEAU.value,
                                                   ProspectStatus.EN_ATTENTE.value,
                                                   ProspectStatus.PENDING.value,
                                                   ProspectStatus.CALLING.value):
                                prospect.status = ProspectStatus.APPELE.value
                    prospect.updated_at = datetime.utcnow()

            ai_agent.end_session(call_id)

            # Enchainement automatique : appeler le prospect suivant si la
            # campagne est toujours active (workflow "passer au numero suivant").
            if call.campaign_id and call.direction == "outbound":
                camp_r = await db.execute(select(Campaign).where(Campaign.id == call.campaign_id))
                camp = camp_r.scalar_one_or_none()
                if camp and camp.status == "active":
                    try:
                        await outbound_service.launch_next(db, camp.id)
                    except Exception as e:
                        logger.error(f"Auto-advance error: {e}")

        await db.flush()

    return {"status": "ok"}


# ──────────────────────────────────────────────────────────────────────────
# 5. Hangup (alias)
# ──────────────────────────────────────────────────────────────────────────
@router.post("/hangup")
async def webhook_hangup(request: Request, db: AsyncSession = Depends(get_db)):
    body: dict[str, Any] = {}
    try:
        raw = await request.body()
        body = json.loads(raw) if raw else {}
    except Exception:
        pass
    body.setdefault("status", "ended")

    class FakeRequest:
        async def json(self): return body

    return await webhook_status(FakeRequest(), db)
