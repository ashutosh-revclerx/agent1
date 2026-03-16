from fastapi import APIRouter, Depends
from app.api.endpoints import health, data, chat, config, target, slack_config, auth
from app.api.endpoints.langfuse_monitor import router as langfuse_monitor_router
from app.core.auth import get_current_user

api_router = APIRouter()

# --- Public Endpoints ---
# These do not require authentication for accessibility (e.g., monitoring heartbeats, login)
api_router.include_router(health.router, tags=["Health"]) 
# Note: health.router contains both public (/health) and protected (/langfuse/status) routes.
# The internal route functions handle their own granular Depends(get_current_user).
api_router.include_router(auth.router, prefix="/api", tags=["Authentication"])
# Note: chat.router has its own multi-auth logic (API Key + User Token) in its internal dependencies
api_router.include_router(chat.router, tags=["Chat"])

# --- Protected Endpoints ---
# Apply Firebase auth as a global requirement for all underlying endpoints
protected_router = APIRouter(dependencies=[Depends(get_current_user)])

protected_router.include_router(langfuse_monitor_router, prefix="/api")
protected_router.include_router(data.router, tags=["Data"])
protected_router.include_router(config.router, tags=["Configuration"])
protected_router.include_router(target.router, tags=["Target Management"])
protected_router.include_router(slack_config.router, tags=["Slack Configuration"])

api_router.include_router(protected_router)
