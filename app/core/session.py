"""
Session Management Utilities
Track and manage user sessions across devices
"""
from datetime import datetime
from typing import Optional, List, Dict
from bson import ObjectId
import secrets
from user_agents import parse

from app.services.mongodb_service import get_db
from app.core.logging import logger
from app.core.time import now_ist, format_ist


def create_session(user_id: str, ip_address: str, user_agent: str) -> str:
    """
    Create a new session for a user
    Returns session_id
    """
    db = get_db()
    if db is None:
        raise Exception("Database unavailable")
    
    # Parse user agent to get device info
    ua = parse(user_agent)
    
    session_id = secrets.token_urlsafe(32)
    created_at = now_ist()
    
    session_doc = {
        "session_id": session_id,
        "user_id": user_id,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "device": {
            "browser": ua.browser.family,
            "browser_version": ua.browser.version_string,
            "os": ua.os.family,
            "os_version": ua.os.version_string,
            "device_type": "mobile" if ua.is_mobile else "tablet" if ua.is_tablet else "desktop"
        },
        "created_at": created_at,
        "created_at_str": format_ist(created_at, include_tz=True),
        "last_active": created_at,
        "last_active_str": format_ist(created_at, include_tz=True),
        "active": True
    }
    
    db.sessions.insert_one(session_doc)
    logger.info(f"[Session] Created session {session_id} for user {user_id}")
    
    return session_id


def validate_session(session_id: str, user_id: str) -> bool:
    """
    Validate that a session exists and is active
    """
    db = get_db()
    if db is None:
        return False
    
    session = db.sessions.find_one({
        "session_id": session_id,
        "user_id": user_id,
        "active": True
    })
    
    if session:
        # Update last active time
        current_time = now_ist()
        db.sessions.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "last_active": current_time,
                    "last_active_str": format_ist(current_time, include_tz=True)
                }
            }
        )
        return True
    
    return False


def revoke_session(session_id: str, user_id: str) -> bool:
    """
    Revoke a specific session
    """
    db = get_db()
    if db is None:
        return False
    
    result = db.sessions.update_one(
        {"session_id": session_id, "user_id": user_id},
        {"$set": {"active": False}}
    )
    
    if result.modified_count > 0:
        logger.info(f"[Session] Revoked session {session_id} for user {user_id}")
        return True
    
    return False


def revoke_all_sessions(user_id: str, except_session_id: Optional[str] = None) -> int:
    """
    Revoke all sessions for a user, optionally except one
    Returns number of sessions revoked
    """
    db = get_db()
    if db is None:
        return 0
    
    query = {"user_id": user_id, "active": True}
    if except_session_id:
        query["session_id"] = {"$ne": except_session_id}
    
    result = db.sessions.update_many(
        query,
        {"$set": {"active": False}}
    )
    
    logger.info(f"[Session] Revoked {result.modified_count} sessions for user {user_id}")
    return result.modified_count


def get_user_sessions(user_id: str, include_inactive: bool = False) -> List[Dict]:
    """
    Get all sessions for a user
    """
    db = get_db()
    if db is None:
        return []
    
    query = {"user_id": user_id}
    if not include_inactive:
        query["active"] = True
    
    sessions = list(db.sessions.find(query).sort("last_active", -1))
    
    # Convert ObjectId to string and format for response
    for session in sessions:
        session["_id"] = str(session["_id"])
    
    return sessions


def cleanup_expired_sessions(days: int = 30) -> int:
    """
    Remove sessions older than specified days
    """
    db = get_db()
    if db is None:
        return 0
    
    from datetime import timedelta
    cutoff_date = now_ist() - timedelta(days=days)
    
    result = db.sessions.delete_many({
        "last_active": {"$lt": cutoff_date}
    })
    
    if result.deleted_count > 0:
        logger.info(f"[Session] Cleaned up {result.deleted_count} expired sessions")
    
    return result.deleted_count
