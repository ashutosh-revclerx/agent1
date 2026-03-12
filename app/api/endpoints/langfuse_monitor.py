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
    rca_type: Optional[str] = Query(default=None, description="Filter by RCA type: batch | session | manual"),
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

    # Use $or to match both scalar langfuse_user_id and array langfuse_user_ids fields
    # This ensures both batch and session RCA records are returned
    if langfuse_user_id:
        if langfuse_user_id not in watched_ids:
            raise HTTPException(status_code=403, detail="You are not authorized to view RCA for this user ID")
        query["$or"] = [
            {"langfuse_user_id": langfuse_user_id},
            {"langfuse_user_ids": langfuse_user_id},
        ]
    else:
        query["$or"] = [
            {"langfuse_user_id": {"$in": watched_ids}},
            {"langfuse_user_ids": {"$in": watched_ids}},
        ]

    # Optional filter by rca_type: "batch" | "session" | "manual"
    if rca_type:
        valid_types = {"batch", "session", "manual"}
        if rca_type not in valid_types:
            raise HTTPException(status_code=400, detail=f"Invalid rca_type. Must be one of: {', '.join(valid_types)}")
        query["rca_type"] = rca_type

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

    if not watched_ids:
        raise HTTPException(status_code=400, detail="You must be watching at least one user to run an RCA")

    # If langfuse_user_id specified, validate permission
    if langfuse_user_id and langfuse_user_id not in watched_ids:
        raise HTTPException(status_code=403, detail="You are not authorized to run RCA for this user ID")

    # Determine which user(s) to run RCA for
    users_to_analyze = [langfuse_user_id] if langfuse_user_id else watched_ids

    loop = asyncio.get_running_loop()
    results = []
    
    for user_id in users_to_analyze:
        result = await loop.run_in_executor(None, run_rca_sync, hours, user_id)
        if result:
            result.pop("raw_analysis", None)
            results.append(result)

    if not results:
        raise HTTPException(
            status_code=422,
            detail="No traces found in the specified time window, or LLM analysis returned no usable result. Try a wider time range."
        )

    # Single user case returns single result for backward compatibility
    if langfuse_user_id:
        return {"message": "RCA analysis complete", "rca": results[0]}
    return {"message": "RCA analysis complete", "rca_results": results}

# ── Missing Phase 1 Endpoints ──────────────────────────────────────────────────

@router.get("/traces/{trace_id}/session")
def get_session_from_trace(trace_id: str, current_user=Depends(get_current_user)):
    """Thin wrapper: extract sessionId from a stored trace document."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    watching_docs = list(db.langfuse_watched_users.find({"added_by": current_user.id}))
    watched_ids = [doc["langfuse_user_id"] for doc in watching_docs]

    trace = db.langfuse_traces.find_one(
        {"trace_id": trace_id, "langfuse_user_id": {"$in": watched_ids}},
        {"_id": 0, "session_id": 1, "trace_id": 1, "langfuse_user_id": 1}
    )
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found or not authorized")

    return {
        "trace_id": trace_id,
        "session_id": trace.get("session_id"),
        "langfuse_user_id": trace.get("langfuse_user_id"),
    }


@router.post("/sessions/{session_id}/store")
def store_session(session_id: str, current_user=Depends(get_current_user)):
    """Snapshot all traces and latest RCA for a session into langfuse_stored_sessions."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    watching_docs = list(db.langfuse_watched_users.find({"added_by": current_user.id}))
    watched_ids = [doc["langfuse_user_id"] for doc in watching_docs]

    traces = list(db.langfuse_traces.find(
        {"session_id": session_id, "langfuse_user_id": {"$in": watched_ids}},
        {"_id": 0}
    ))
    if not traces:
        raise HTTPException(status_code=404, detail="No traces found for this session, or not authorized")

    # Only store sessions that have at least one error trace
    error_count = sum(1 for t in traces if t.get("status") == "error")
    if error_count == 0:
        raise HTTPException(
            status_code=400,
            detail="This session has no error traces — only errored sessions are stored"
        )

    latencies = [t["latency_s"] for t in traces if t.get("latency_s")]
    metrics = {
        "total_traces": len(traces),
        "total_input_tokens": sum(t.get("input_tokens", 0) for t in traces),
        "total_output_tokens": sum(t.get("output_tokens", 0) for t in traces),
        "total_tokens": sum(t.get("total_tokens", 0) for t in traces),
        "total_cost_usd": round(sum(t.get("cost_usd", 0) for t in traces), 6),
        "avg_latency_s": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
        "error_count": sum(1 for t in traces if t.get("status") == "error"),
        "models_used": list({t.get("model") for t in traces if t.get("model")}),
    }

    user_ids_in_session = list({t.get("langfuse_user_id") for t in traces if t.get("langfuse_user_id")})
    latest_rca = db.langfuse_rca.find_one(
        {"$or": [
            {"langfuse_user_id": {"$in": user_ids_in_session}},
            {"langfuse_user_ids": {"$in": user_ids_in_session}},
        ]},
        {"_id": 0, "raw_analysis": 0},
        sort=[("timestamp", -1)]
    )

    doc = {
        "session_id": session_id,
        "stored_by": current_user.id,
        "stored_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "langfuse_user_ids": user_ids_in_session,
        "metrics": metrics,
        "traces": traces,
        "latest_rca": latest_rca or {},
    }

    db.langfuse_stored_sessions.replace_one(
        {"session_id": session_id, "stored_by": current_user.id},
        doc,
        upsert=True,
    )
    return {"message": f"Session {session_id} stored successfully", "metrics": metrics}


@router.get("/sessions/stored")
def list_stored_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    """List all sessions manually stored by the current user."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    sessions = list(
        db.langfuse_stored_sessions.find(
            {"stored_by": current_user.id},
            {"_id": 0, "traces": 0}  # exclude heavy traces array from list view
        ).sort("stored_at", -1).limit(limit)
    )
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/sessions/stored/{session_id}")
def get_stored_session(session_id: str, current_user=Depends(get_current_user)):
    """Retrieve a specific stored session including its traces and RCA."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    doc = db.langfuse_stored_sessions.find_one(
        {"session_id": session_id, "stored_by": current_user.id},
        {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Stored session not found or not authorized")
    return doc


@router.delete("/sessions/stored/{session_id}")
def delete_stored_session(session_id: str, current_user=Depends(get_current_user)):
    """Remove a stored session from the database."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    result = db.langfuse_stored_sessions.delete_one(
        {"session_id": session_id, "stored_by": current_user.id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Stored session not found or not authorized")
    return {"message": f"Session {session_id} deleted"}


@router.post("/pipeline/run/{trace_id}")
async def run_full_pipeline(trace_id: str, current_user=Depends(get_current_user)):
    """
    Full Phase 1 pipeline trigger for a single errored trace.
    Steps: fetch trace → collect session metrics → store + RCA in parallel → return result.
    """
    import asyncio
    from app.services.langfuse_ingestion_service import run_rca_sync

    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    watching_docs = list(db.langfuse_watched_users.find({"added_by": current_user.id}))
    watched_ids = [doc["langfuse_user_id"] for doc in watching_docs]

    # Step 1: Fetch and validate the trace
    trace = db.langfuse_traces.find_one(
        {"trace_id": trace_id, "langfuse_user_id": {"$in": watched_ids}},
        {"_id": 0}
    )
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found or not authorized")
    if trace.get("status") != "error":
        raise HTTPException(status_code=400, detail="Trace is not an error trace — pipeline only runs on errored traces")

    session_id = trace.get("session_id")
    langfuse_user_id = trace.get("langfuse_user_id")

    # Step 2: Collect traces for RCA context
    # - If session_id exists: fetch all traces in that session
    # - If no session_id: fetch last 5 traces for the same user as fallback context
    if session_id:
        session_traces = list(db.langfuse_traces.find(
            {"session_id": session_id},
            {"_id": 0}
        ))
    else:
        session_traces = list(
            db.langfuse_traces.find(
                {"langfuse_user_id": langfuse_user_id},
                {"_id": 0}
            ).sort("timestamp", -1).limit(5)
        )
        logger.info(
            f"[Pipeline] No session_id on trace {trace_id} — "
            f"using last 5 traces for user {langfuse_user_id} as RCA context"
        )

    # Step 3: Build metrics
    latencies = [t["latency_s"] for t in session_traces if t.get("latency_s")]
    metrics = {
        "total_traces": len(session_traces),
        "total_tokens": sum(t.get("total_tokens", 0) for t in session_traces),
        "total_cost_usd": round(sum(t.get("cost_usd", 0) for t in session_traces), 6),
        "avg_latency_s": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
        "error_count": sum(1 for t in session_traces if t.get("status") == "error"),
    }

    # Step 4: Store session to DB
    user_ids = list({t.get("langfuse_user_id") for t in session_traces if t.get("langfuse_user_id")})
    latest_rca_snapshot = db.langfuse_rca.find_one(
        {"$or": [
            {"langfuse_user_id": {"$in": user_ids}},
            {"langfuse_user_ids": {"$in": user_ids}},
        ]},
        {"_id": 0, "raw_analysis": 0},
        sort=[("timestamp", -1)]
    )
    db.langfuse_stored_sessions.replace_one(
        {"session_id": session_id, "stored_by": current_user.id},
        {
            "session_id": session_id,
            "stored_by": current_user.id,
            "stored_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "trigger_trace_id": trace_id,
            "langfuse_user_ids": user_ids,
            "metrics": metrics,
            "traces": session_traces,
            "latest_rca": latest_rca_snapshot or {},
        },
        upsert=True,
    )

    # Step 5: Trigger RCA
    loop = asyncio.get_running_loop()
    rca_result = await loop.run_in_executor(None, run_rca_sync, 1, langfuse_user_id)
    if rca_result:
        rca_result.pop("raw_analysis", None)
        rca_result.pop("_id", None)

    return {
        "message": "Pipeline complete",
        "trace_id": trace_id,
        "session_id": session_id,
        "metrics": metrics,
        "stored": True,
        "rca": rca_result or {"message": "No anomalies detected in the RCA window"},
    }