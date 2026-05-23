"""
Session Controller
Manages chat session lifecycle and metadata
"""
import uuid
from typing import Optional, Dict
from datetime import datetime, timedelta, timezone
from app.core.logging import logger


class SessionManager:
    """Manage chat sessions and their metadata"""

    def __init__(self):
        self.active_sessions = {}  # In-memory cache

    def create_session(self, db, user_id: str) -> str:
        """Create a new chat session. user_id is required for ownership tracking."""
        session_id = str(uuid.uuid4())
        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc),
            "last_activity": datetime.now(timezone.utc),
            "message_count": 0,
            "total_tokens": 0,
        }
        if db is not None:
            try:
                db.chat_sessions.insert_one(session_data)
                logger.info(f"[Session] Created new session: {session_id}")
            except Exception as e:
                logger.error(f"[Session] Failed to create session in DB: {e}")
        self.active_sessions[session_id] = session_data
        return session_id

    def get_session(self, session_id: str, db, owner_id: str = None) -> Optional[Dict]:
        """Get session by ID. Pass owner_id to enforce ownership."""
        if session_id in self.active_sessions:
            cached = self.active_sessions[session_id]
            # Enforce ownership on cached hit if owner_id provided
            if owner_id and cached.get("user_id") != owner_id:
                return None
            return cached
        if db is not None:
            try:
                query = {"session_id": session_id}
                if owner_id:
                    query["user_id"] = owner_id
                session = db.chat_sessions.find_one(query)
                if session:
                    self.active_sessions[session_id] = session
                    return session
            except Exception as e:
                logger.error(f"[Session] Failed to fetch session: {e}")
        return None

    def update_session(self, session_id: str, db, tokens: int = 0):
        """Update session activity"""
        now = datetime.now(timezone.utc)
        if db is not None:
            try:
                db.chat_sessions.update_one(
                    {"session_id": session_id},
                    {
                        "$set": {"last_activity": now},
                        "$inc": {"message_count": 1, "total_tokens": tokens},
                    },
                )
            except Exception as e:
                logger.error(f"[Session] Failed to update session: {e}")

        if session_id in self.active_sessions:
            self.active_sessions[session_id]["last_activity"] = now
            self.active_sessions[session_id]["message_count"] = self.active_sessions[session_id].get("message_count", 0) + 1
            self.active_sessions[session_id]["total_tokens"] = self.active_sessions[session_id].get("total_tokens", 0) + tokens

    def cleanup_old_sessions(self, db, hours: int = 24):
        """Remove sessions older than specified hours"""
        if db is None:
            return
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        try:
            result = db.chat_sessions.delete_many({"last_activity": {"$lt": cutoff}})
            if result.deleted_count > 0:
                logger.info(f"[Session] Cleaned up {result.deleted_count} old sessions")

            to_remove = [
                sid for sid, data in self.active_sessions.items()
                if data.get("last_activity", datetime.now(timezone.utc)) < cutoff
            ]
            for sid in to_remove:
                del self.active_sessions[sid]
        except Exception as e:
            logger.error(f"[Session] Cleanup failed: {e}")


# Global session manager instance
session_manager = SessionManager()