"""
NexCall AI v2 — Router Agents IA
"""
import logging
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent import Agent
from app.services.agent_service import agent_service
from app.services.ai_agent import ai_agent

router = APIRouter(prefix="/api/agents", tags=["agents"])
logger = logging.getLogger(__name__)


class AgentCreate(BaseModel):
    name:             str
    service:          str
    description:      Optional[str] = None
    system_prompt:    str
    script_intro:     Optional[str] = None
    script_questions: Optional[str] = None
    script_objections:Optional[str] = None
    business_context: Optional[str] = None
    rules:            Optional[str] = None
    voice:            str = "nova"
    tone:             str = "professionnel"
    ai_provider:      str = "openai"
    ai_model:         str = "gpt-4o"
    ai_temperature:   float = 0.7
    language:         str = "fr"
    ringover_number:  Optional[str] = None
    transfer_number:  Optional[str] = None
    transfer_score:   int = 70
    is_active:        bool = True


class AgentUpdate(BaseModel):
    name:             Optional[str] = None
    description:      Optional[str] = None
    system_prompt:    Optional[str] = None
    script_intro:     Optional[str] = None
    script_questions: Optional[str] = None
    script_objections:Optional[str] = None
    business_context: Optional[str] = None
    rules:            Optional[str] = None
    voice:            Optional[str] = None
    tone:             Optional[str] = None
    ai_provider:      Optional[str] = None
    ai_model:         Optional[str] = None
    ai_temperature:   Optional[float] = None
    language:         Optional[str] = None
    ringover_number:  Optional[str] = None
    transfer_number:  Optional[str] = None
    transfer_score:   Optional[int] = None
    is_active:        Optional[bool] = None


class TestAgentRequest(BaseModel):
    message:      str = "Bonjour, je suis interesse par une mutuelle sante."
    prospect_name:str = "Jean Dupont"


@router.get("")
async def list_agents(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    agents = await agent_service.get_all(db, active_only=active_only)
    return [a.to_dict() for a in agents]


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    return await agent_service.get_stats(db)


@router.get("/defaults")
async def get_default_services():
    """Retourne les services disponibles avec leurs prompts par defaut."""
    from app.services.agent_service import DEFAULT_AGENTS, DEFAULT_PROMPTS
    return {
        "services": [
            {"key": svc, "label": label, "default_agent": next(
                (a for a in DEFAULT_AGENTS if a["service"] == svc), None
            )}
            for svc, label in Agent.SERVICE_LABELS.items()
        ],
        "voices": ["nova", "shimmer", "alloy", "echo", "fable", "onyx"],
        "tones": ["professionnel", "chaleureux", "dynamique", "empathique"],
        "providers": [
            {"key": "openai", "label": "OpenAI", "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]},
            {"key": "anthropic", "label": "Anthropic (Claude)", "models": ["claude-sonnet-4-5", "claude-opus-4-1", "claude-haiku-4-5"]},
            {"key": "mistral", "label": "Mistral", "models": ["mistral-large-latest", "mistral-small-latest"]},
            {"key": "custom", "label": "Autre (compatible OpenAI)", "models": []},
        ],
    }


@router.post("/seed")
async def seed_agents(db: AsyncSession = Depends(get_db)):
    """Cree les 6 agents par defaut si la table est vide."""
    created = await agent_service.seed_default_agents(db)
    return {"success": True, "created": created, "message": f"{created} agents crees"}


@router.get("/{agent_id}")
async def get_agent(agent_id: int, db: AsyncSession = Depends(get_db)):
    a = await agent_service.get_by_id(db, agent_id)
    if not a:
        raise HTTPException(404, "Agent non trouve")
    return a.to_dict()


@router.post("", status_code=201)
async def create_agent(body: AgentCreate, db: AsyncSession = Depends(get_db)):
    a = await agent_service.create(db, body.model_dump())
    return a.to_dict()


@router.put("/{agent_id}")
async def update_agent(agent_id: int, body: AgentUpdate, db: AsyncSession = Depends(get_db)):
    a = await agent_service.update(db, agent_id, body.model_dump(exclude_none=True))
    if not a:
        raise HTTPException(404, "Agent non trouve")
    return a.to_dict()


@router.delete("/{agent_id}")
async def delete_agent(agent_id: int, db: AsyncSession = Depends(get_db)):
    a = await agent_service.get_by_id(db, agent_id)
    if not a:
        raise HTTPException(404, "Agent non trouve")
    await db.delete(a)
    return {"success": True}


@router.post("/{agent_id}/test")
async def test_agent(agent_id: int, body: TestAgentRequest, db: AsyncSession = Depends(get_db)):
    """Teste un agent IA avec un message simulé."""
    agent = await agent_service.get_by_id(db, agent_id)
    if not agent:
        raise HTTPException(404, "Agent non trouve")
    if not agent.is_active:
        raise HTTPException(400, "Agent inactif")

    test_call_id = f"test_{agent_id}_{int(datetime.utcnow().timestamp()*1000)}"
    result = await ai_agent.chat(
        call_id       = test_call_id,
        user_message  = body.message,
        agent         = agent,
        prospect_name = body.prospect_name,
    )
    ai_agent.end_session(test_call_id)
    return {
        "agent":         agent.to_dict(),
        "user_message":  body.message,
        "ai_response":   result["text"],
        "qualification": result.get("qualification"),
        "error":         result.get("error"),
    }


@router.post("/{agent_id}/toggle")
async def toggle_agent(agent_id: int, db: AsyncSession = Depends(get_db)):
    agent = await agent_service.get_by_id(db, agent_id)
    if not agent:
        raise HTTPException(404, "Agent non trouve")
    agent.is_active = not agent.is_active
    agent.updated_at = datetime.utcnow()
    return {"success": True, "is_active": agent.is_active}
