from app.routers.pages         import router as pages_router
from app.routers.calls         import router as calls_router
from app.routers.leads         import router as leads_router
from app.routers.campaigns     import router as campaigns_router
from app.routers.configuration import router as config_router
from app.routers.webhooks      import router as webhooks_router
from app.routers.agents        import router as agents_router
from app.routers.prospects     import router as prospects_router
from app.routers.contacts      import router as contacts_router
from app.routers.blacklist     import router as blacklist_router
from app.routers.scripts       import router as scripts_router
from app.routers.analytics     import router as analytics_router

__all__ = [
    "pages_router", "calls_router", "leads_router", "campaigns_router",
    "config_router", "webhooks_router", "agents_router", "prospects_router",
    "contacts_router", "blacklist_router", "scripts_router", "analytics_router",
]
