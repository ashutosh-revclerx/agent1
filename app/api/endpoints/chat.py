"""
Chat API Endpoints
Enables external chatbots to query the system with session context.
"""
from fastapi import APIRouter, Depends, HTTPException, Body, Header
from pydantic import BaseModel
from typing import Optional, Literal, List

from app.core.auth import get_current_user
from app.services.chat_service import chat_service
from app.core.logging import logger

from app.services.mongodb_service import get_db

router = APIRouter(prefix="/chat", tags=["chat"])

# Simple API Key for LibreChat integration
SYSTEM_API_KEY = "librechat_dev_key"

async def get_chat_user(
    current_user = Depends(get_current_user_optional),
    x_api_key: Optional[str] = Header(None)
):
    """Bypass auth if a valid system API key is provided."""
    if current_user:
        return current_user
    
    if x_api_key == SYSTEM_API_KEY:
        # Return a dummy system user
        from app.schemas.user import User
        return User(id="librechat_system", username="librechat", email="bot@system", active=True)
    
    raise HTTPException(status_code=401, detail="Authentication required")

class ChatQuery(BaseModel):
    session_id: str
    type: Literal["monitoring", "langfuse"]
    message: str

@router.post("/query")
async def query_chat(
    query: ChatQuery,
    current_user = Depends(get_chat_user)
):
    """
    Query the LLM about a specific system session.
    The agent will fetch metrics/traces context before answering.
    """
    try:
        logger.info(f"[Chat] Query for {query.type} session {query.session_id} by user {current_user.id}")
        
        response = await chat_service.query_session(
            session_id=query.session_id,
            context_type=query.type,
            user_id=current_user.id,
            message=query.message
        )
        
        if not response:
            raise HTTPException(status_code=500, detail="Failed to get response from LLM")
            
        return {
            "response": response,
            "session_id": query.session_id,
            "type": query.type
        }
        
    except Exception as e:
        logger.error(f"[Chat] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sessions")
async def list_sessions(
    limit: int = 5,
    db = Depends(get_db)
):
    """List recent monitoring and langfuse sessions for the chatbot to choose from."""
    return chat_service.list_recent_sessions(db, limit)