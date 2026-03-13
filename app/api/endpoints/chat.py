"""
Chat Routes
AI chat endpoints with session management.

Security controls applied:
  - Authentication required (get_current_user)
  - Per-user sliding-window rate limiter (in-memory, no extra deps)
  - Payload size validated at schema level (ChatMessage)
  - Context keys and values sanitised before entering prompt
  - Session ownership enforced on resume
"""
import asyncio
import time
import threading
from collections import deque
from fastapi import APIRouter, Depends, HTTPException, Request
from app.schemas.chat import ChatMessage, ChatResponse
from app.schemas.user import User
from app.services.mongodb_service import get_db
from app.services.session_service import session_manager
from app.services.llm_service import ask_llm
from app.core.logging import logger
from app.core.auth import get_current_user

router = APIRouter()

# ── Rate limiter ───────────────────────────────────────────────────────────────
# Sliding-window: at most RATE_LIMIT_MAX_CALLS per RATE_LIMIT_WINDOW_SECONDS
# per authenticated user_id.  Thread-safe; no external dependency required.

RATE_LIMIT_MAX_CALLS = 20        # requests
RATE_LIMIT_WINDOW_SECONDS = 60   # per minute

_rate_lock = threading.Lock()
_rate_windows: dict[str, deque] = {}   # user_id → deque of call timestamps


def _check_rate_limit(user_id: str) -> None:
    """
    Raise HTTP 429 if the user has exceeded the rate limit.
    Uses a sliding window over the last RATE_LIMIT_WINDOW_SECONDS.
    """
    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS

    with _rate_lock:
        if user_id not in _rate_windows:
            _rate_windows[user_id] = deque()
        window = _rate_windows[user_id]

        # Evict timestamps outside the window
        while window and window[0] < cutoff:
            window.popleft()

        if len(window) >= RATE_LIMIT_MAX_CALLS:
            oldest = window[0]
            retry_after = int(RATE_LIMIT_WINDOW_SECONDS - (now - oldest)) + 1
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )

        window.append(now)


# ── Allowed context keys ───────────────────────────────────────────────────────
# Whitelist keeps user-controlled strings out of sensitive prompt positions.

_ALLOWED_CONTEXT_KEYS = {
    "page", "tab", "component", "selected_ip",
    "time_range", "severity", "environment",
}

MAX_CONTEXT_VALUE_LEN = 200   # per value


def _sanitise_context(raw: dict) -> dict:
    """
    Keep only whitelisted keys with string values up to MAX_CONTEXT_VALUE_LEN.
    Silently drops unknown keys so callers don't learn the whitelist via errors.
    """
    result = {}
    for k, v in raw.items():
        if k not in _ALLOWED_CONTEXT_KEYS:
            continue
        result[k] = str(v)[:MAX_CONTEXT_VALUE_LEN]
    return result


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(
    message: ChatMessage,
    user: User = Depends(get_current_user),   # ← authentication enforced
):
    """
    Chat with the AI assistant.
    Maintains conversation context through authenticated sessions.
    """
    # 1. Rate limit check
    _check_rate_limit(str(user.id))

    db = get_db()

    # 2. Session — resume only if it belongs to the requesting user
    session_id = message.session_id
    if session_id:
        existing = session_manager.get_session(session_id, db, owner_id=str(user.id))
        if not existing:
            # Either doesn't exist or belongs to a different user — start fresh
            logger.warning(
                f"[Chat] session_id {session_id!r} not found for user {user.id}; "
                "creating new session"
            )
            session_id = None

    if not session_id:
        session_id = session_manager.create_session(db, user_id=str(user.id))
        logger.info(f"[Chat] New session: {session_id} for user {user.id}")
    else:
        logger.info(f"[Chat] Continuing session: {session_id}")

    # 3. Build prompt — sanitise context before interpolation
    safe_context = _sanitise_context(message.context)
    context_str = ""
    if safe_context:
        lines = ["Context:"] + [f"- {k}: {v}" for k, v in safe_context.items()]
        context_str = "\n".join(lines)

    prompt = (
        "You are a helpful DevOps assistant.\n"
        f"User asks: {message.message}\n"
        f"\n{context_str}\n"
        "Provide a helpful, concise answer. Explain technical concepts simply if asked."
    )

    # 4. Call LLM
    try:
        result = await asyncio.get_running_loop().run_in_executor(
            None,
            ask_llm,
            prompt,
            "AI Chat",
            {"user_message": message.message, **safe_context},
            session_id,
            str(user.id),
        )
        response_text, tokens = result if result else (None, 0)
    except Exception as e:
        logger.error(f"[Chat] LLM service error: {e}")
        raise HTTPException(
            status_code=503,
            detail="AI service temporarily unavailable. Please try again shortly.",
        )

    # 5. Update session metrics
    session_manager.update_session(session_id, db, tokens)

    return ChatResponse(
        response=response_text or "Sorry, I'm having trouble connecting to the AI service.",
        session_id=session_id,
    )