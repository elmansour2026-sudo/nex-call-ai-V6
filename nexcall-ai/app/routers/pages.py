"""
NexCall AI v3 — Pages HTML
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")

def page(name, active):
    async def _p(request: Request):
        return templates.TemplateResponse(name, {"request": request, "active": active})
    return _p

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request, "active": "dashboard"})

@router.get("/contacts", response_class=HTMLResponse)
async def contacts(request: Request):
    return templates.TemplateResponse("contacts.html", {"request": request, "active": "contacts"})

@router.get("/agents", response_class=HTMLResponse)
async def agents(request: Request):
    return templates.TemplateResponse("agents.html", {"request": request, "active": "agents"})

@router.get("/agents/{agent_id}", response_class=HTMLResponse)
async def agent_detail(request: Request, agent_id: int):
    return templates.TemplateResponse("agent_detail.html", {"request": request, "active": "agents", "agent_id": agent_id})

@router.get("/scripts", response_class=HTMLResponse)
async def scripts(request: Request):
    return templates.TemplateResponse("scripts.html", {"request": request, "active": "scripts"})

@router.get("/agent-settings", response_class=HTMLResponse)
async def agent_settings(request: Request):
    return templates.TemplateResponse("agent_settings.html", {"request": request, "active": "agent_settings"})

@router.get("/campaigns", response_class=HTMLResponse)
async def campaigns(request: Request):
    return templates.TemplateResponse("campaigns_v2.html", {"request": request, "active": "campaigns"})

@router.get("/calls", response_class=HTMLResponse)
async def calls(request: Request):
    return templates.TemplateResponse("calls.html", {"request": request, "active": "calls"})

@router.get("/analytics", response_class=HTMLResponse)
async def analytics(request: Request):
    return templates.TemplateResponse("analytics.html", {"request": request, "active": "analytics"})

@router.get("/crm", response_class=HTMLResponse)
async def crm(request: Request):
    return templates.TemplateResponse("crm.html", {"request": request, "active": "crm"})

@router.get("/leads", response_class=HTMLResponse)
async def leads(request: Request):
    return templates.TemplateResponse("leads.html", {"request": request, "active": "leads"})

@router.get("/blacklist", response_class=HTMLResponse)
async def blacklist(request: Request):
    return templates.TemplateResponse("blacklist.html", {"request": request, "active": "blacklist"})

@router.get("/configuration", response_class=HTMLResponse)
async def configuration(request: Request):
    return templates.TemplateResponse("configuration.html", {"request": request, "active": "configuration"})
