"""
Data Retrieval Routes - Pagination + Correct IST fields + User Filtering
Fixes:
- sort by created_at_ist / timestamp_ist (not created_at)
- consistent timestamp output for UI
- supports skip+limit so frontend can fetch ALL rows
- user authentication and data isolation
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Depends
from datetime import datetime, timedelta
from app.services.mongodb_service import get_db
from app.schemas.user import User
from app.core.auth import get_current_user

router = APIRouter()


def _iso(d):
    if isinstance(d, datetime):
        return d.isoformat()
    return d


def _stringify_id(doc: dict, field: str = "_id"):
    if field in doc:
        doc[field] = str(doc[field])
    return doc


def _clamp_limit(limit: int, default: int, max_limit: int):
    try:
        limit = int(limit)
    except Exception:
        limit = default
    if limit <= 0:
        limit = default
    return min(limit, max_limit)


@router.get("/stats")
def get_stats(user: User = Depends(get_current_user)):
    """Get stats for current user only"""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    user_filter = {"user_id": user.id}

    email_config = db.email_config.find_one(user_filter) or {}
    email_enabled = email_config.get("enabled", False)
    email_recipients = len(email_config.get("recipients", []))

    slack_config = db.slack_config.find_one(user_filter) or {}
    slack_enabled = slack_config.get("enabled", False)
    slack_webhook = slack_config.get("webhook_url", "")

    return {
        "collections": {
            "metrics_batches": {"total": db.metrics_batches.count_documents(user_filter)},
            "incidents": {"total": db.incidents.count_documents(user_filter)},
            "metrics": {"total": db.metrics.count_documents(user_filter)},
            "anomalies": {
                "total": db.anomalies.count_documents(user_filter),
                "open": db.anomalies.count_documents({**user_filter, "severity": {"$in": ["critical", "high"]}}),
                "analyzed": db.rca.count_documents(user_filter),
            },
            "chat_sessions": {
                "total": db.chat_sessions.count_documents(user_filter),
                "active": db.chat_sessions.count_documents({
                    **user_filter,
                    "last_activity": {"$gte": datetime.utcnow() - timedelta(hours=1)}
                }),
            },
        },
        "notifications": {
            "email": {"enabled": email_enabled, "recipients": email_recipients},
            "slack": {"enabled": slack_enabled, "configured": bool(slack_webhook)},
        },
    }


@router.get("/grafana-url")
def get_grafana_url(
    instance: str = Query(..., description="Server instance (e.g., 192.168.1.4:9182)"),
    _user: User = Depends(get_current_user)
):
    """
    Generate Grafana dashboard URL for a specific instance
    Returns URL with pre-selected instance, 30-minute time range, and 30s auto-refresh
    """
    # Base Grafana URL (can be configured via environment variable)
    grafana_base = "http://localhost:3001"
    
    # Dashboard UID from the JSON file
    dashboard_uid = "server-monitoring"
    
    from urllib.parse import quote
    # Build URL with parameters — URL-encode instance to prevent injection
    grafana_url = (
        f"{grafana_base}/d/{dashboard_uid}/server-monitoring"
        f"?orgId=1"
        f"&var-instance={quote(instance, safe='')}"
        f"&from=now-30m"
        f"&to=now"
        f"&refresh=30s"
    )
    
    return {
        "grafana_url": grafana_url,
        "instance": instance,
        "dashboard": "Server Monitoring"
    }



@router.get("/batches")
def get_batches(
    user: User = Depends(get_current_user),
    limit: int = Query(10000, ge=1),
    skip: int = Query(0, ge=0),
):
    """Get batches for current user only"""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    limit = _clamp_limit(limit, default=10000, max_limit=100000)

    # Prefer new IST fields, fallback to older ones if present
    sort_fields = [("collected_at_ist", -1), ("collected_at", -1), ("timestamp", -1)]

    cursor = db.metrics_batches.find({"user_id": user.id}).sort(sort_fields).skip(skip).limit(limit)
    docs = list(cursor)

    for d in docs:
        _stringify_id(d)
        # send UI-friendly timestamps
        d["collected_at"] = _iso(d.get("collected_at_ist") or d.get("collected_at") or d.get("timestamp"))
        d["window_start"] = _iso(d.get("window_start_ist") or d.get("window_start"))
        d["window_end"] = _iso(d.get("window_end_ist") or d.get("window_end"))

    return {"batches": docs}


@router.get("/incidents")
def get_incidents(
    user: User = Depends(get_current_user),
    limit: int = Query(10000, ge=1),
    skip: int = Query(0, ge=0),
):
    """Get incidents for current user only"""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    limit = _clamp_limit(limit, default=10000, max_limit=100000)
    sort_fields = [("created_at_ist", -1), ("created_at", -1), ("timestamp", -1)]

    docs = list(db.incidents.find({"user_id": user.id}).sort(sort_fields).skip(skip).limit(limit))
    for d in docs:
        _stringify_id(d)
        if "batch_id" in d:
            d["batch_id"] = str(d.get("batch_id") or "")
        # Consistent timestamp for frontend
        d["timestamp"] = _iso(d.get("created_at_ist") or d.get("created_at") or d.get("timestamp"))
        d["window_start"] = _iso(d.get("window_start_ist") or d.get("window_start"))
        d["window_end"] = _iso(d.get("window_end_ist") or d.get("window_end"))

    return {"incidents": docs}


@router.get("/anomalies")
def get_anomalies(
    user: User = Depends(get_current_user),
    limit: int = Query(10000, ge=1),
    skip: int = Query(0, ge=0),
):
    """
    Get anomalies for current user only
    Supports pagination: /anomalies?limit=10000&skip=0
    """
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    limit = _clamp_limit(limit, default=10000, max_limit=100000)

    # ✅ Prefer new IST field, fallback to old
    sort_fields = [("created_at_ist", -1), ("created_at", -1), ("timestamp", -1)]

    docs = list(db.anomalies.find({"user_id": user.id}).sort(sort_fields).skip(skip).limit(limit))
    for d in docs:
        _stringify_id(d)

        # ✅ UI timestamp always populated
        d["timestamp"] = _iso(d.get("created_at_ist") or d.get("created_at") or d.get("timestamp"))

        if "incident_id" in d:
            d["incident_id"] = str(d.get("incident_id") or "")
        if "batch_id" in d:
            d["batch_id"] = str(d.get("batch_id") or "")

        if "severity" not in d:
            d["severity"] = "medium"

    return {"anomalies": docs}


@router.get("/rca")
def get_rca(
    user: User = Depends(get_current_user),
    limit: int = Query(10000, ge=1),
    skip: int = Query(0, ge=0),
):
    """
    Get RCA results for current user only
    Supports pagination: /rca?limit=10000&skip=0
    Combines standard Prometheus RCAs with Langfuse RCAs.
    """
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    limit = _clamp_limit(limit, default=10000, max_limit=100000)

    # 1. Fetch standard RCAs for the user
    standard_docs = list(db.rca.find({"user_id": user.id}))
    for d in standard_docs:
        _stringify_id(d)
        d["timestamp"] = _iso(d.get("timestamp_ist") or d.get("timestamp") or d.get("created_at_ist") or d.get("created_at"))
        d["source"] = "prometheus"
        # Convert all ObjectId fields to strings
        if "batch_id" in d and d["batch_id"]:
            d["batch_id"] = str(d["batch_id"])
        if "incident_id" in d and d["incident_id"]:
            d["incident_id"] = str(d["incident_id"])
        if "anomaly_id" in d and d["anomaly_id"]:
            d["anomaly_id"] = str(d["anomaly_id"])
        d["window_start"] = _iso(d.get("window_start_ist") or d.get("window_start"))
        d["window_end"] = _iso(d.get("window_end_ist") or d.get("window_end"))

    # 2. Fetch Langfuse RCAs (filtered by watched users)
    langfuse_docs = []
    try:
        _lf_collections = db.list_collection_names()
    except Exception:
        _lf_collections = []
    if "langfuse_rca" in _lf_collections:
        watching_docs = list(db.langfuse_watched_users.find({"added_by": user.id}))
        watched_ids = [doc["langfuse_user_id"] for doc in watching_docs]
        
        if watched_ids:
            langfuse_docs = list(db.langfuse_rca.find({"langfuse_user_id": {"$in": watched_ids}}))
        
        for d in langfuse_docs:
            _stringify_id(d)
            d["timestamp"] = _iso(d.get("timestamp"))
            d["source"] = "langfuse"
            d["metric"] = "Langfuse LLM Traces"
            
            # Map Langfuse fields to standard RCA UI fields
            inst = d.get("langfuse_user_id")
            d["instance"] = f"User: {inst}" if inst else "All Users (Incremental)"
            d["cause"] = d.get("root_cause", "No root cause identified.")
            
            # Extract actions from recommendations and join them for the "fix" field
            recs = d.get("recommendations", [])
            if isinstance(recs, list) and len(recs) > 0:
                if isinstance(recs[0], dict):
                    d["fix"] = [r.get("action", "") for r in recs]
                else:
                    d["fix"] = recs
            else:
                d["fix"] = "No specific recommendations."

    # 3. Combine, sort, and paginate
    all_docs = standard_docs + langfuse_docs
    # Sort descending by timestamp
    all_docs.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    
    # Apply skip and limit
    paginated_docs = all_docs[skip : skip + limit]

    return {"rca": paginated_docs}


@router.get("/prom-metrics")
def get_prom_metrics(
    user: User = Depends(get_current_user),
    limit: int = Query(10000, ge=1),
    skip: int = Query(0, ge=0),
):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    limit = _clamp_limit(limit, default=10000, max_limit=100000)
    docs = list(db.metrics.find({"user_id": user.id}).sort([("timestamp", -1)]).skip(skip).limit(limit))
    for d in docs:
        _stringify_id(d)
        d["timestamp"] = _iso(d.get("timestamp"))

    return {"metrics": docs}


@router.get("/api/sessions")
def get_sessions(
    user: User = Depends(get_current_user),
    limit: int = Query(10000, ge=1),
    skip: int = Query(0, ge=0),
):
    db = get_db()
    if db is None:
        return {"sessions": []}

    limit = _clamp_limit(limit, default=10000, max_limit=100000)
    sessions = list(db.chat_sessions.find({"user_id": user.id}).sort("last_activity", -1).skip(skip).limit(limit))
    for s in sessions:
        _stringify_id(s)
        s["created_at"] = _iso(s.get("created_at"))
        s["last_activity"] = _iso(s.get("last_activity"))

    return {"sessions": sessions}


@router.get("/api/sessions/{session_id}")
def get_session_details(session_id: str, user: User = Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    from app.services.session_service import session_manager
    session = session_manager.get_session(session_id, db, owner_id=user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    _stringify_id(session)
    session["created_at"] = _iso(session.get("created_at"))
    session["last_activity"] = _iso(session.get("last_activity"))
    return session


@router.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, user: User = Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    result = db.chat_sessions.delete_one({"session_id": session_id, "user_id": user.id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")

    from app.services.session_service import session_manager
    if session_id in session_manager.active_sessions:
        del session_manager.active_sessions[session_id]

    return {"message": "Session deleted successfully"}


# ============ IP-FILTERED ENDPOINTS ============

@router.get("/metrics/by-ip")
def get_metrics_by_ip(
    ip: str,
    user: User = Depends(get_current_user),
    limit: int = Query(10000, ge=1),
    skip: int = Query(0, ge=0),
):
    """Get metrics filtered by IP address for current user"""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    
    limit = _clamp_limit(limit, default=10000, max_limit=100000)
    docs = list(db.metrics_batches.find({"ip": ip, "user_id": user.id}).sort([("collected_at_ist", -1)]).skip(skip).limit(limit))
    
    for d in docs:
        _stringify_id(d)
        d["collected_at"] = _iso(d.get("collected_at_ist") or d.get("collected_at"))
        d["window_start"] = _iso(d.get("window_start_ist") or d.get("window_start"))
        d["window_end"] = _iso(d.get("window_end_ist") or d.get("window_end"))
    
    return {"metrics": docs, "total": len(docs), "ip": ip}


@router.get("/anomalies/by-ip")
def get_anomalies_by_ip(
    ip: str,
    user: User = Depends(get_current_user),
    limit: int = Query(10000, ge=1),
    skip: int = Query(0, ge=0),
):
    """Get anomalies filtered by IP address for current user"""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    
    limit = _clamp_limit(limit, default=10000, max_limit=100000)
    docs = list(db.anomalies.find({"ip": ip, "user_id": user.id}).sort([("created_at_ist", -1)]).skip(skip).limit(limit))
    
    for d in docs:
        _stringify_id(d)
        d["timestamp"] = _iso(d.get("created_at_ist") or d.get("created_at") or d.get("timestamp"))
        if "incident_id" in d:
            d["incident_id"] = str(d.get("incident_id") or "")
        if "batch_id" in d:
            d["batch_id"] = str(d.get("batch_id") or "")
        if "severity" not in d:
            d["severity"] = "medium"
    
    return {"anomalies": docs, "total": len(docs), "ip": ip}


@router.get("/incidents/by-ip")
def get_incidents_by_ip(
    ip: str,
    user: User = Depends(get_current_user),
    limit: int = Query(10000, ge=1),
    skip: int = Query(0, ge=0),
):
    """Get incidents filtered by IP address for current user"""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    
    limit = _clamp_limit(limit, default=10000, max_limit=100000)
    docs = list(db.incidents.find({"ip": ip, "user_id": user.id}).sort([("created_at_ist", -1)]).skip(skip).limit(limit))
    
    for d in docs:
        _stringify_id(d)
        if "batch_id" in d:
            d["batch_id"] = str(d.get("batch_id") or "")
        d["timestamp"] = _iso(d.get("created_at_ist") or d.get("created_at") or d.get("timestamp"))
        d["window_start"] = _iso(d.get("window_start_ist") or d.get("window_start"))
        d["window_end"] = _iso(d.get("window_end_ist") or d.get("window_end"))
    
    return {"incidents": docs, "total": len(docs), "ip": ip}


@router.get("/rca/by-ip")
def get_rca_by_ip(
    ip: str,
    user: User = Depends(get_current_user),
    limit: int = Query(10000, ge=1),
    skip: int = Query(0, ge=0),
):
    """Get RCA results filtered by IP address for current user"""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    
    limit = _clamp_limit(limit, default=10000, max_limit=100000)
    docs = list(db.rca.find({"ip": ip, "user_id": user.id}).sort([("timestamp_ist", -1)]).skip(skip).limit(limit))
    
    for d in docs:
        _stringify_id(d)
        d["timestamp"] = _iso(d.get("timestamp_ist") or d.get("timestamp") or d.get("created_at_ist"))
        # Convert all ObjectId fields to strings
        if "batch_id" in d and d["batch_id"]:
            d["batch_id"] = str(d["batch_id"])
        if "incident_id" in d and d["incident_id"]:
            d["incident_id"] = str(d["incident_id"])
        if "anomaly_id" in d and d["anomaly_id"]:
            d["anomaly_id"] = str(d["anomaly_id"])
        d["window_start"] = _iso(d.get("window_start_ist") or d.get("window_start"))
        d["window_end"] = _iso(d.get("window_end_ist") or d.get("window_end"))
    
    return {"rca": docs, "total": len(docs), "ip": ip}


@router.get("/batches/by-ip")
def get_batches_by_ip(
    ip: str,
    user: User = Depends(get_current_user),
    limit: int = Query(10000, ge=1),
    skip: int = Query(0, ge=0),
):
    """Get batch results filtered by IP address for current user"""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    
    limit = _clamp_limit(limit, default=10000, max_limit=100000)
    docs = list(db.metrics_batches.find({"ip": ip, "user_id": user.id}).sort([("collected_at_ist", -1)]).skip(skip).limit(limit))
    
    for d in docs:
        _stringify_id(d)
        d["collected_at"] = _iso(d.get("collected_at_ist") or d.get("collected_at"))
        d["window_start"] = _iso(d.get("window_start_ist") or d.get("window_start"))
        d["window_end"] = _iso(d.get("window_end_ist") or d.get("window_end"))
    
    return {"batches": docs, "total": len(docs), "ip": ip}