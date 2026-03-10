"""
Langfuse Monitor Endpoints
CRUD for watched users + read traces/stats from MongoDB.
Follows the same patterns as other endpoints in app/api/endpoints/.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.services.mongodb_service import get_db
from app.core.logging import logger

# Match auth import pattern from other endpoint files in your project
# e.g. from app.core.auth import get_current_user
# Replace the import below with whatever your project uses:
from app.core.auth import get_current_user

router = APIRouter(prefix="/langfuse-monitor", tags=["langfuse-monitor"])


class WatchedUserIn(BaseModel):
    langfuse_user_id: str
    label: Optional[str] = None


# ── Watched Users ──────────────────────────────────────────────────────────────

@router.get("/watched-users")
def get_watched_users(current_user=Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    docs = list(db.langfuse_watched_users.find({"added_by": current_user.id}, {"_id": 0}))
    return {"users": docs}


@router.post("/watched-users")
def add_watched_user(body: WatchedUserIn, current_user=Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    existing = db.langfuse_watched_users.find_one(
        {"langfuse_user_id": body.langfuse_user_id}
    )
    if existing:
        raise HTTPException(status_code=400, detail="User already being watched")

    db.langfuse_watched_users.insert_one({
        "langfuse_user_id": body.langfuse_user_id,
        "label": body.label or body.langfuse_user_id,
        "added_at": datetime.now(timezone.utc).isoformat(),
        "added_by": current_user.id,
    })
    return {"message": f"Now watching {body.langfuse_user_id}"}


@router.delete("/watched-users/{langfuse_user_id:path}")
def remove_watched_user(langfuse_user_id: str, current_user=Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    result = db.langfuse_watched_users.delete_one(
        {"langfuse_user_id": langfuse_user_id, "added_by": current_user.id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Watched user not found or you don't have permission to remove it")
    return {"message": f"Stopped watching {langfuse_user_id}"}


# ── Stats & Traces ─────────────────────────────────────────────────────────────

@router.get("/stats")
def get_stats(
    hours: int = Query(default=24, ge=1, le=168),
    langfuse_user_id: Optional[str] = Query(default=None),
    current_user=Depends(get_current_user),
):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    watching_docs = list(db.langfuse_watched_users.find({"added_by": current_user.id}))
    watched_ids = [doc["langfuse_user_id"] for doc in watching_docs]

    if not watched_ids:
        # If the user isn't watching anyone, return empty stats without querying traces
        return {
            "total_traces": 0, "total_input_tokens": 0, "total_output_tokens": 0,
            "total_tokens": 0, "total_cost_usd": 0.0, "avg_latency_s": 0.0,
            "error_count": 0, "models_used": {}, "active_users": {}, "hours_window": hours
        }

    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    query = {"timestamp": {"$gte": since}}
    
    if langfuse_user_id:
        if langfuse_user_id not in watched_ids:
            raise HTTPException(status_code=403, detail="You are not authorized to view stats for this user ID")
        query["langfuse_user_id"] = langfuse_user_id
    else:
        query["langfuse_user_id"] = {"$in": watched_ids}

    traces = list(db.langfuse_traces.find(query, {"_id": 0}))

    total_input = sum(t.get("input_tokens", 0) for t in traces)
    total_output = sum(t.get("output_tokens", 0) for t in traces)
    total_cost = sum(t.get("cost_usd", 0) for t in traces)
    latencies = [t["latency_s"] for t in traces if t.get("latency_s")]
    errors = sum(1 for t in traces if t.get("status") == "error")

    models: dict = {}
    users: dict = {}
    for t in traces:
        m = t.get("model")
        u = t.get("langfuse_user_id")
        if m:
            models[m] = models.get(m, 0) + 1
        if u:
            users[u] = users.get(u, 0) + 1

    return {
        "total_traces": len(traces),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_input + total_output,
        "total_cost_usd": round(total_cost, 6),
        "avg_latency_s": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
        "error_count": errors,
        "models_used": models,
        "active_users": users,
        "hours_window": hours,
    }


@router.get("/traces")
def get_traces(
    hours: int = Query(default=24, ge=1, le=168),
    langfuse_user_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user=Depends(get_current_user),
):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    watching_docs = list(db.langfuse_watched_users.find({"added_by": current_user.id}))
    watched_ids = [doc["langfuse_user_id"] for doc in watching_docs]

    if not watched_ids:
        return {"traces": [], "count": 0}

    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    query = {"timestamp": {"$gte": since}}

    if langfuse_user_id:
        if langfuse_user_id not in watched_ids:
            raise HTTPException(status_code=403, detail="You are not authorized to view traces for this user ID")
        query["langfuse_user_id"] = langfuse_user_id
    else:
        query["langfuse_user_id"] = {"$in": watched_ids}

    traces = list(
        db.langfuse_traces.find(query, {"_id": 0})
        .sort("timestamp", -1)
        .limit(limit)
    )
    return {"traces": traces, "count": len(traces)}


# ── RCA ────────────────────────────────────────────────────────────────────────

@router.get("/rca")
def get_rca_results(
    hours: int = Query(default=24, ge=1, le=168),
    langfuse_user_id: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    watching_docs = list(db.langfuse_watched_users.find({"added_by": current_user.id}))
    watched_ids = [doc["langfuse_user_id"] for doc in watching_docs]

    if not watched_ids:
        return {"rca": [], "count": 0}

    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    query = {"timestamp": {"$gte": since}}

    # RCA records are sometimes generated generally (incremental) without a langfuse_user_id.
    # To be secure, we must either only show RCAs tied specifically to the user's watched IDs.
    if langfuse_user_id:
        if langfuse_user_id not in watched_ids:
            raise HTTPException(status_code=403, detail="You are not authorized to view RCA for this user ID")
        query["langfuse_user_id"] = langfuse_user_id
    else:
        query["langfuse_user_id"] = {"$in": watched_ids}

    results = list(
        db.langfuse_rca.find(query, {"_id": 0, "raw_analysis": 0})
        .sort("timestamp", -1)
        .limit(limit)
    )
    return {"rca": results, "count": len(results)}


@router.post("/rca/run")
async def run_rca_now(
    hours: int = Query(default=1, ge=1, le=24),
    langfuse_user_id: Optional[str] = Query(default=None),
    current_user=Depends(get_current_user),
):
    """Trigger an on-demand RCA analysis."""
    import asyncio
    from app.services.langfuse_ingestion_service import run_rca_sync

    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    watching_docs = list(db.langfuse_watched_users.find({"added_by": current_user.id}))
    watched_ids = [doc["langfuse_user_id"] for doc in watching_docs]

    if not langfuse_user_id:
        raise HTTPException(status_code=400, detail="You must specify a langfuse_user_id to run an RCA on")

    if langfuse_user_id not in watched_ids:
        raise HTTPException(status_code=403, detail="You are not authorized to run RCA for this user ID")

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, run_rca_sync, hours, langfuse_user_id)

    if not result:
        return {"message": "No traces found to analyze or LLM analysis failed", "rca": None}

    # Remove raw_analysis from response
    result.pop("raw_analysis", None)
    return {"message": "RCA analysis complete", "rca": result}