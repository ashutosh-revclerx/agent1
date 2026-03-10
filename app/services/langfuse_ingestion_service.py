"""
Langfuse Ingestion Service
Polls Langfuse every 2 minutes for new traces from watched user IDs
and stores them in MongoDB (langfuse_traces collection).
"""
import asyncio
import requests
from datetime import datetime, timedelta, timezone

from app.core.config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
from app.services.mongodb_service import get_db
from app.core.logging import logger

POLL_INTERVAL_SECONDS = 120  # 2 minutes


def _auth():
    return (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _get_watched_user_ids_sync() -> list:
    """Sync: fetch watched userIds from MongoDB."""
    db = get_db()
    if db is None:
        return []
    try:
        docs = list(db.langfuse_watched_users.find({}))
        return [doc["langfuse_user_id"] for doc in docs]
    except Exception as e:
        logger.error(f"[Langfuse] Failed to fetch watched users: {e}")
        return []


def _ingest_for_user_sync(langfuse_user_id: str) -> int:
    """Sync: poll Langfuse and store new traces for one user. Returns count ingested."""
    db = get_db()
    if db is None:
        return 0

    now = datetime.now(timezone.utc)
    since = now - timedelta(minutes=3)  # 3 min overlap to avoid missing traces

    try:
        response = requests.get(
            f"{LANGFUSE_HOST}/api/public/traces",
            auth=_auth(),
            params={
                "limit": 50,
                "fromTimestamp": _ts(since),
                "toTimestamp": _ts(now),
                "userId": langfuse_user_id,
            },
            timeout=15,
        )
        response.raise_for_status()
        traces = response.json().get("data", [])
    except Exception as e:
        logger.error(f"[Langfuse] Failed to fetch traces for {langfuse_user_id}: {e}")
        return 0

    ingested = 0
    for trace in traces:
        trace_id = trace["id"]

        # Skip if already ingested
        if db.langfuse_traces.find_one({"trace_id": trace_id}):
            continue

        # Fetch observations for token/model data
        input_tokens = 0
        output_tokens = 0
        model = None
        status = "success"

        try:
            obs_response = requests.get(
                f"{LANGFUSE_HOST}/api/public/observations",
                auth=_auth(),
                params={"traceId": trace_id, "type": "GENERATION", "limit": 100},
                timeout=15,
            )
            obs_response.raise_for_status()
            observations = obs_response.json().get("data", [])

            for obs in observations:
                usage = obs.get("usage", {}) or {}
                input_tokens += int(usage.get("input", 0) or 0)
                output_tokens += int(usage.get("output", 0) or 0)
                model = obs.get("model") or model
                if obs.get("level") == "ERROR":
                    status = "error"
        except Exception as e:
            logger.warning(f"[Langfuse] Failed to fetch observations for {trace_id}: {e}")

        doc = {
            "trace_id": trace_id,
            "langfuse_user_id": langfuse_user_id,
            "name": trace.get("name"),
            "timestamp": trace["timestamp"],
            "latency_s": trace.get("latency"),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cost_usd": round(float(trace.get("totalCost") or 0.0), 6),
            "model": model,
            "session_id": trace.get("sessionId"),
            "status": status,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            db.langfuse_traces.insert_one(doc)
            ingested += 1
        except Exception as e:
            logger.error(f"[Langfuse] Failed to insert trace {trace_id}: {e}")

    logger.info(f"[Langfuse] user={langfuse_user_id} | found={len(traces)} | new={ingested}")
    return ingested


async def poll_langfuse():
    """
    Background task: polls Langfuse every 2 minutes.
    Matches the pattern used by BatchMonitor in main.py.
    """
    logger.info("[Langfuse] Polling service started (interval=2min)")
    while True:
        try:
            loop = asyncio.get_event_loop()
            watched = await loop.run_in_executor(None, _get_watched_user_ids_sync)

            if not watched:
                logger.debug("[Langfuse] No watched users, skipping poll")
            else:
                for user_id in watched:
                    await loop.run_in_executor(None, _ingest_for_user_sync, user_id)

        except Exception as e:
            logger.error(f"[Langfuse] Poll loop error: {e}")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)