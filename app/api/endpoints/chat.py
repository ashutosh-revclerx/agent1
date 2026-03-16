"""
Chat API Endpoints
Enables external chatbots (LibreChat) to query the system with session context.
"""
import os
import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Body, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Literal

from app.core.auth import get_current_user_optional
from app.schemas.user import User
from app.services.chat_service import chat_service
from app.core.logging import logger
from app.services.mongodb_service import get_db

router = APIRouter(prefix="/chat", tags=["chat"])

_SYSTEM_USER = User(id="librechat_system", username="librechat", email="librechat@system", active=True)


async def get_chat_user(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None),           # fallback for query-string auth
    current_user: Optional[User] = Depends(get_current_user_optional)
) -> User:
    """Accept JWT, header API Key, query-string API Key, or default to system user."""
    if current_user:
        return current_user

    valid_api_key = os.getenv("LIBRECHAT_API_KEY", "librechat_dev_key")
    provided = x_api_key or api_key
    if provided:
        if provided == valid_api_key:
            return _SYSTEM_USER
        logger.warning(f"[Chat] Invalid API key: {provided!r}")

    logger.info("[Chat] No auth — defaulting to system user")
    return _SYSTEM_USER


class ChatQuery(BaseModel):
    session_id: str
    type: Literal["monitoring", "langfuse"]
    message: str


class LatestQuery(BaseModel):
    message: str = "Give me a full system health summary"


@router.post("/query")
async def query_chat(
    query: ChatQuery,
    current_user: User = Depends(get_chat_user)
):
    """
    Query the LLM about a specific monitoring or Langfuse session.
    Fetches full context (metrics, anomalies, RCA, traces) before answering.
    """
    try:
        logger.info(f"[Chat] Session query: type={query.type} session={query.session_id} user={current_user.id}")
        response = await chat_service.query_session(
            session_id=query.session_id,
            context_type=query.type,
            user_id=current_user.id,
            message=query.message,
        )
        if not response:
            raise HTTPException(status_code=500, detail="LLM returned no response")
        return {"response": response, "session_id": query.session_id, "type": query.type}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Chat] Query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/latest")
async def query_latest(
    body: LatestQuery = Body(default_factory=LatestQuery),
    current_user: User = Depends(get_chat_user)
):
    """
    Query the LLM about the MOST RECENT system state without needing a session ID.
    Returns an AI-generated health summary based on the latest monitoring incident 
    and Langfuse RCA. Use this for 'What is the current system health?' style questions.
    """
    try:
        logger.info(f"[Chat] Latest query by user={current_user.id}: {body.message[:60]}")
        response = await chat_service.query_latest(
            user_id=current_user.id,
            message=body.message,
        )
        if not response:
            raise HTTPException(status_code=500, detail="LLM returned no response")
        return {"response": response, "type": "latest_snapshot"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Chat] Latest query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_sessions(
    limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_chat_user)
):
    """
    List the most recent monitoring and Langfuse sessions.
    Returns sessions enriched with severity, anomaly counts, health scores, and error rates.
    Call this first to discover session IDs before calling /chat/query.
    """
    db = get_db()
    result = chat_service.list_recent_sessions(db, limit)
    return result


@router.get("/openapi.json", include_in_schema=False)
async def chat_openapi_spec():
    """Serve the LibreChat-compatible OpenAPI Actions spec."""
    spec_path = Path(__file__).parents[3] / "LibreChat" / "monitoring-actions.json"
    if not spec_path.exists():
        raise HTTPException(status_code=404, detail="OpenAPI spec not found")
    return JSONResponse(content=json.loads(spec_path.read_text()))
