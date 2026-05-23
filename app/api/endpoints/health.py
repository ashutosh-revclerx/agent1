from typing import Optional
from fastapi import APIRouter, Depends
from app.core.config import PROM_URL, LLM_MODEL, SLACK_WEBHOOK_URL, LANGFUSE_HOST
from app.core.time import now_ist
from app.services.langfuse_service import is_langfuse_enabled, get_langfuse_client
from app.services.slack_service import slack_is_configured
from app.core.auth import get_current_user, get_current_user_optional
from app.schemas.user import User

router = APIRouter()


@router.get("/health")
def root(user: Optional[User] = Depends(get_current_user_optional)):
    """Root endpoint - system heartbeat (Public/Enriched)"""
    # Basic public status
    base_status = {
        "status": "running",
        "timestamp": "heartbeat"
    }
    
    # If authenticated, add details for dashboard
    if user:
        from app.core.time import format_ist
        base_status.update({
            "prometheus": PROM_URL,
            "llm": LLM_MODEL,
            "langfuse": "enabled" if is_langfuse_enabled() else "disabled",
            "slack": "enabled" if slack_is_configured(user_id=user.id) else "disabled",
            "current_time": format_ist(now_ist(), include_tz=False),
            "timezone": "IST (UTC+5:30)"
        })
    
    return base_status


@router.get("/langfuse/status")
def get_langfuse_status(user: User = Depends(get_current_user)):
    """Langfuse integration status (Protected)"""
    langfuse = get_langfuse_client()
    status = {
        "installed": langfuse is not None,
        "enabled": is_langfuse_enabled(),
        "version": "v3.12+",
        "host": LANGFUSE_HOST if is_langfuse_enabled() else None,
        "connected": False,
        "session_tracking": True,
        "api_methods": {
            "tracing": "start_as_current_observation()",
            "sessions": "propagate_attributes(session_id=...)",
            "decorator": "@observe",
        },
    }
    if langfuse and is_langfuse_enabled():
        try:
            langfuse.auth_check()
            status["connected"] = True
        except Exception as e:
            status["error"] = str(e)
    return status


@router.get("/agent/slack-status")
def slack_status(user: User = Depends(get_current_user)):
    """Slack integration status (Protected)"""
    from app.core.config import SLACK_ENABLED
    return {
        "enabled_flag": bool(SLACK_ENABLED),
        "webhook_url_set": bool((SLACK_WEBHOOK_URL or "").strip()),
        "active": slack_is_configured(user_id=user.id),
    }
