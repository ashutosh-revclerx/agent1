from fastapi import APIRouter
from app.api.endpoints import health, data, chat, config, target, slack_config, auth

api_router = APIRouter()
from app.api.endpoints.langfuse_monitor import router as langfuse_monitor_router
api_router.include_router(langfuse_monitor_router)
api_router.include_router(auth.router, prefix="/api", tags=["Authentication"])
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(data.router, tags=["Data"])
api_router.include_router(chat.router, tags=["Chat"])
api_router.include_router(config.router, tags=["Configuration"])
api_router.include_router(target.router, tags=["Target Management"])
api_router.include_router(slack_config.router, tags=["Slack Configuration"])
