"""
Langfuse Service
----------------
Centralizes Langfuse initialization and helper utilities.

Provides:
  - Langfuse client initialization and management
  - Batch session ID generation for grouping LLM calls
  - Time window calculation for batch processing
  - Context managers for session propagation
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Iterator, Optional, Tuple

from app.core.config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
from app.core.logging import logger

# Try to import Langfuse (optional dependency)
try:
    from langfuse import Langfuse
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    logger.info("[Langfuse]  Not installed")


# Global state
langfuse = None
LANGFUSE_ENABLED = False


def initialize_langfuse():
    """Initialize Langfuse client and test connection"""
    global langfuse, LANGFUSE_ENABLED

    if not LANGFUSE_AVAILABLE:
        logger.info("[Langfuse]  Not installed")
        return

    if not (LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY):
        logger.info("[Langfuse]  Disabled (API keys not set in .env)")
        return

    try:
        langfuse = Langfuse(
            public_key=LANGFUSE_PUBLIC_KEY,
            secret_key=LANGFUSE_SECRET_KEY,
            host=LANGFUSE_HOST,
        )
        langfuse.auth_check()
        LANGFUSE_ENABLED = True
        logger.info("[Langfuse] ✅ Connected successfully!")
    except Exception as e:
        logger.error(f"[Langfuse] ❌ Failed to initialize: {e}")
        langfuse = None
        LANGFUSE_ENABLED = False


def get_langfuse_client():
    """Get Langfuse client instance (or None if disabled)"""
    return langfuse if LANGFUSE_ENABLED else None


def is_langfuse_enabled() -> bool:
    """Check if Langfuse is enabled and available"""
    return LANGFUSE_ENABLED


def flush_langfuse():
    """Flush remaining Langfuse data to server (called at shutdown)"""
    if langfuse and LANGFUSE_ENABLED:
        try:
            logger.info("[Langfuse] Flushing remaining data...")
            langfuse.flush()
            logger.info("[Langfuse] ✅ Flush complete")
        except Exception as e:
            logger.warning(f"[Langfuse] Flush error: {e}")


# ==========================
# Batch Processing Helpers
# ==========================

def _floor_to_interval(dt: datetime, minutes: int) -> datetime:
    """
    Round a datetime down to the nearest interval.

    Example:
        _floor_to_interval(datetime(2026, 1, 29, 3, 16, 45), 1)
        Returns: datetime(2026, 1, 29, 3, 16, 0)

        _floor_to_interval(datetime(2026, 1, 29, 3, 43, 0), 30)
        Returns: datetime(2026, 1, 29, 3, 30, 0)
    """
    if minutes <= 0:
        return dt.replace(second=0, microsecond=0)

    minute_bucket = (dt.minute // minutes) * minutes
    return dt.replace(minute=minute_bucket, second=0, microsecond=0)


def make_batch_window(
    now_utc: Optional[datetime] = None,
    interval_minutes: int = 30
) -> Tuple[datetime, datetime]:
    """
    Calculate the current batch window (start, end) in UTC.

    Args:
        now_utc: Current time in UTC (uses datetime.utcnow() if None)
        interval_minutes: Window size in minutes (default: 30)

    Returns:
        Tuple of (window_start, window_end) as naive UTC datetimes
    """
    now = now_utc or datetime.utcnow()
    start = _floor_to_interval(now, interval_minutes)
    end = start + timedelta(minutes=interval_minutes)
    return start, end


def make_batch_session_id(
    now_utc: Optional[datetime] = None,
    interval_minutes: int = 30,
    prefix: str = "batch",
) -> str:
    """
    Generate a stable session ID for a batch window.

    The same time window always generates the same session ID,
    allowing all LLM calls within a batch to be grouped together.

    Returns:
        Session ID in format: "prefix:YYYYMMDDHHMM-YYYYMMDDHHMM"
    """
    start, end = make_batch_window(now_utc=now_utc, interval_minutes=interval_minutes)
    return f"{prefix}:{start.strftime('%Y%m%d%H%M')}-{end.strftime('%Y%m%d%H%M')}"


@contextmanager
def langfuse_session(session_id: Optional[str]) -> Iterator[None]:
    """
    No-op context manager kept for API compatibility.

    Session grouping is handled by passing session_id explicitly to
    langfuse.trace() in llm_service.py — no context propagation needed.
    The previous propagate_attributes approach was removed because it
    called start_as_current_observation which is not available in v2.57.0.
    """
    yield