"""
Langfuse Ingestion Service
Polls Langfuse every 2 minutes for new traces from watched user IDs
and stores them in MongoDB (langfuse_traces collection).
Includes LLM-based RCA analysis of ingested traces.
"""
import asyncio
import json
import uuid
import requests
from datetime import datetime, timedelta, timezone

from app.core.config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
from app.services.mongodb_service import get_db
from app.services.llm_service import ask_llm
from app.core.helpers import parse_json
from app.core.logging import logger

POLL_INTERVAL_SECONDS = 120  # 2 minutes


def _utc_iso() -> str:
    """Return current UTC time as ISO string with Z suffix for consistent MongoDB queries."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


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
            "timestamp": trace["timestamp"],  # Already Z-suffix from Langfuse API
            "latency_s": trace.get("latency"),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cost_usd": round(float(trace.get("totalCost") or 0.0), 6),
            "model": model,
            "session_id": trace.get("sessionId"),
            "status": status,
            "ingested_at": _utc_iso(),
        }

        try:
            db.langfuse_traces.insert_one(doc)
            ingested += 1
        except Exception as e:
            logger.error(f"[Langfuse] Failed to insert trace {trace_id}: {e}")

    logger.info(f"[Langfuse] user={langfuse_user_id} | found={len(traces)} | new={ingested}")
    return ingested


# ── RCA Analysis ───────────────────────────────────────────────────────────────

def _get_rolling_baseline(db, hours: int = 1) -> dict:
    """Get aggregate stats from the last N hours as baseline context for the LLM."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    all_traces = list(db.langfuse_traces.find({"timestamp": {"$gte": since}}, {"_id": 0}))

    if not all_traces:
        return {"total": 0}

    latencies = [t["latency_s"] for t in all_traces if t.get("latency_s")]
    errors = sum(1 for t in all_traces if t.get("status") == "error")

    return {
        "total": len(all_traces),
        "errors": errors,
        "error_rate_pct": round(errors / len(all_traces) * 100, 1) if all_traces else 0,
        "avg_latency": round(sum(latencies) / len(latencies), 2) if latencies else 0,
        "max_latency": round(max(latencies), 2) if latencies else 0,
        "total_tokens": sum(t.get("total_tokens", 0) for t in all_traces),
        "total_cost": round(sum(t.get("cost_usd", 0) for t in all_traces), 4),
    }


def _build_rca_prompt(traces: list, hours: int) -> str:
    """Build a prompt for the full-window manual RCA analysis."""
    trace_lines = []
    for t in traces:
        trace_lines.append(
            f"  - name={t.get('name', 'unknown')} | user={t.get('langfuse_user_id')} | "
            f"model={t.get('model')} | tokens={t.get('total_tokens', 0)} | "
            f"cost=${t.get('cost_usd', 0)} | latency={t.get('latency_s', '?')}s | "
            f"status={t.get('status')} | time={t.get('timestamp')}"
        )

    schema = {
        "summary": "string - brief overview of the trace data",
        "anomalies": [
            {
                "type": "error_spike|latency_spike|cost_anomaly|throughput_drop",
                "severity": "low|medium|high|critical",
                "description": "string",
                "affected_model": "string",
                "affected_trace": "string",
                "evidence": "string",
            }
        ],
        "root_cause": "string - collective root cause analysis for the period",
        "recommendations": [
            {"priority": "immediate|short_term|long_term", "action": "string"}
        ],
        "health_score": "0-100 integer (100 = perfectly healthy)",
    }

    return f"""You are an expert LLM operations analyst reviewing Langfuse traces.
You are running a full analysis on {len(traces)} traces from the last {hours} hours.

TRACES TO EVALUATE:
{chr(10).join(trace_lines)}

INSTRUCTIONS:
1. Review the performance, costs, and errors across all these traces.
2. Group related errors or slow responses.
3. Identify collective root causes if multiple traces are failing for the same reason.
4. Return ONLY valid JSON (no markdown, no code fences) matching the schema.

SCHEMA:
{json.dumps(schema, indent=2)}

RETURN ONLY JSON:"""


def _build_incremental_rca_prompt(new_traces: list, baseline: dict) -> str:
    """Build a prompt that focuses on NEW traces only, with rolling baseline context."""
    trace_lines = []
    for t in new_traces:
        trace_lines.append(
            f"  - name={t.get('name', 'unknown')} | user={t.get('langfuse_user_id')} | "
            f"model={t.get('model')} | tokens={t.get('total_tokens', 0)} | "
            f"cost=${t.get('cost_usd', 0)} | latency={t.get('latency_s', '?')}s | "
            f"status={t.get('status')} | time={t.get('timestamp')}"
        )

    new_errors = sum(1 for t in new_traces if t.get("status") == "error")
    new_latencies = [t["latency_s"] for t in new_traces if t.get("latency_s")]
    new_avg_lat = round(sum(new_latencies) / len(new_latencies), 2) if new_latencies else 0

    schema = {
        "noteworthy": "boolean - true if any anomaly or concern found, false if all normal",
        "anomalies": [
            {
                "type": "error_spike|latency_spike|cost_anomaly|throughput_drop",
                "severity": "low|medium|high|critical",
                "description": "string",
                "affected_model": "string",
                "affected_trace": "string",
                "evidence": "string",
            }
        ],
        "root_cause": "string - root cause analysis (empty string if nothing noteworthy)",
        "summary": "string - brief overview",
        "recommendations": [
            {"priority": "immediate|short_term|long_term", "action": "string"}
        ],
        "health_score": "0-100 integer (100 = perfectly healthy)",
    }

    return f"""You are an expert LLM operations analyst. You are reviewing NEWLY ingested Langfuse traces.

ROLLING BASELINE (last 1 hour):
  Total traces: {baseline.get('total', 0)}
  Error rate: {baseline.get('error_rate_pct', 0)}%
  Avg latency: {baseline.get('avg_latency', 0)}s
  Max latency: {baseline.get('max_latency', 0)}s
  Total tokens: {baseline.get('total_tokens', 0):,}
  Total cost: ${baseline.get('total_cost', 0)}

NEW TRACES TO EVALUATE ({len(new_traces)} traces):
{chr(10).join(trace_lines)}

New trace stats: {new_errors} errors, avg_latency={new_avg_lat}s

INSTRUCTIONS:
1. Compare the new traces against the rolling baseline
2. If everything looks NORMAL - set noteworthy=false, health_score=100, empty anomalies
3. If you detect issues (errors, latency spikes vs baseline, unusual costs) - set noteworthy=true and provide details
4. Be practical: a single slow trace is not necessarily an anomaly
5. Return ONLY valid JSON (no markdown, no code fences)

SCHEMA:
{json.dumps(schema, indent=2)}

RETURN ONLY JSON:"""


def run_rca_on_new_traces(new_trace_ids: list) -> dict:
    """Run RCA on specific newly ingested traces, with rolling baseline context.
    Returns the RCA result dict, or empty dict if nothing noteworthy."""
    db = get_db()
    if db is None:
        return {}

    # Fetch the actual new trace documents
    new_traces = list(db.langfuse_traces.find(
        {"trace_id": {"$in": new_trace_ids}}, {"_id": 0}
    ))
    if not new_traces:
        return {}

    # Get rolling baseline for context
    baseline = _get_rolling_baseline(db, hours=1)

    prompt = _build_incremental_rca_prompt(new_traces, baseline)
    session_id = f"langfuse-rca-{uuid.uuid4().hex[:8]}"

    try:
        result = ask_llm(prompt, "Langfuse Incremental RCA", {
            "new_trace_count": len(new_traces),
            "baseline_total": baseline.get("total", 0),
        }, session_id=session_id)
        if not result:
            logger.error("[Langfuse RCA] LLM returned no result")
            return {}
        text, _ = result
        analysis = parse_json(text) if text else {}
    except Exception as e:
        logger.error(f"[Langfuse RCA] LLM call failed: {e}")
        return {}

    if not analysis:
        return {}

    # If the LLM says nothing noteworthy, skip storing
    noteworthy = analysis.get("noteworthy", True)
    health = analysis.get("health_score", 100)
    anomalies = analysis.get("anomalies", [])

    if not noteworthy and health >= 95 and len(anomalies) == 0:
        logger.info(f"[Langfuse RCA] All normal (health={health}), skipping storage")
        return {}

    # Store RCA result
    rca_doc = {
        "timestamp": _utc_iso(),
        "window_hours": 0,  # incremental, not a fixed window
        "langfuse_user_id": None,
        "total_traces": len(new_traces),
        "total_errors": sum(1 for t in new_traces if t.get("status") == "error"),
        "total_cost_usd": round(sum(t.get("cost_usd", 0) for t in new_traces), 6),
        "summary": analysis.get("summary", ""),
        "root_cause": analysis.get("root_cause", ""),
        "anomalies": anomalies,
        "recommendations": analysis.get("recommendations", []),
        "health_score": health,
        "raw_analysis": analysis,
    }

    try:
        db.langfuse_rca.insert_one(rca_doc)
        logger.info(
            f"[Langfuse RCA] Stored: anomalies={len(anomalies)}, "
            f"health={health}, new_traces={len(new_traces)}"
        )
    except Exception as e:
        logger.error(f"[Langfuse RCA] Failed to store RCA: {e}")

    rca_doc.pop("_id", None)
    return rca_doc


def run_rca_sync(hours: int = 1, langfuse_user_id: str = None) -> dict:
    """Run full-window RCA analysis (used by the manual 'Run Analysis' button).
    Analyzes ALL traces in the given time window."""
    db = get_db()
    if db is None:
        return {}

    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    query = {"timestamp": {"$gte": since}}
    if langfuse_user_id:
        query["langfuse_user_id"] = langfuse_user_id

    traces = list(db.langfuse_traces.find(query, {"_id": 0}))
    if not traces:
        logger.debug("[Langfuse RCA] No traces to analyze")
        return {}

    prompt = _build_rca_prompt(traces, hours)
    session_id = f"langfuse-rca-{uuid.uuid4().hex[:8]}"

    try:
        result = ask_llm(prompt, "Langfuse RCA Analysis", {
            "trace_count": len(traces),
            "hours": hours,
            "langfuse_user_id": langfuse_user_id,
        }, session_id=session_id)
        if not result:
            logger.error("[Langfuse RCA] LLM returned no result")
            return {}
        text, _ = result
        analysis = parse_json(text) if text else {}
    except Exception as e:
        logger.error(f"[Langfuse RCA] LLM call failed: {e}")
        return {}

    if not analysis:
        return {}

    # Store RCA result
    rca_doc = {
        "timestamp": _utc_iso(),
        "window_hours": hours,
        "langfuse_user_id": langfuse_user_id,
        "total_traces": len(traces),
        "total_errors": sum(1 for t in traces if t.get("status") == "error"),
        "total_cost_usd": round(sum(t.get("cost_usd", 0) for t in traces), 6),
        "summary": analysis.get("summary", ""),
        "root_cause": analysis.get("root_cause", ""),
        "anomalies": analysis.get("anomalies", []),
        "recommendations": analysis.get("recommendations", []),
        "health_score": analysis.get("health_score", 100),
        "raw_analysis": analysis,
    }

    try:
        db.langfuse_rca.insert_one(rca_doc)
        logger.info(
            f"[Langfuse RCA] Stored: anomalies={len(rca_doc['anomalies'])}, "
            f"health={rca_doc['health_score']}, traces={len(traces)}"
        )
    except Exception as e:
        logger.error(f"[Langfuse RCA] Failed to store RCA: {e}")

    rca_doc.pop("_id", None)
    return rca_doc


async def poll_langfuse():
    """
    Background task: polls Langfuse every 2 minutes.
    After ingesting traces, runs incremental RCA on only the NEW traces.
    """
    # Guard: don't start polling if Langfuse keys are not configured
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY or not LANGFUSE_HOST:
        logger.warning("[Langfuse] Polling DISABLED — missing LANGFUSE_PUBLIC_KEY, SECRET_KEY, or HOST")
        return

    logger.info("[Langfuse] Polling service started (interval=2min)")
    while True:
        try:
            loop = asyncio.get_running_loop()
            watched = await loop.run_in_executor(None, _get_watched_user_ids_sync)

            if not watched:
                logger.debug("[Langfuse] No watched users, skipping poll")
            else:
                new_trace_ids = []
                for user_id in watched:
                    count = await loop.run_in_executor(None, _ingest_for_user_sync, user_id)
                    if count > 0:
                        # Collect the IDs of just-ingested traces
                        recent = await loop.run_in_executor(
                            None, _get_recent_trace_ids, user_id, count
                        )
                        new_trace_ids.extend(recent)

                # Run incremental RCA on only the new traces
                if new_trace_ids:
                    logger.info(f"[Langfuse RCA] Analyzing {len(new_trace_ids)} new traces")
                    await loop.run_in_executor(None, run_rca_on_new_traces, new_trace_ids)

        except Exception as e:
            logger.error(f"[Langfuse] Poll loop error: {e}")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def _get_recent_trace_ids(langfuse_user_id: str, count: int) -> list:
    """Fetch the most recently ingested trace_ids for a user."""
    db = get_db()
    if db is None:
        return []
    try:
        docs = list(
            db.langfuse_traces.find(
                {"langfuse_user_id": langfuse_user_id},
                {"trace_id": 1, "_id": 0}
            ).sort("ingested_at", -1).limit(count)
        )
        return [d["trace_id"] for d in docs]
    except Exception as e:
        logger.error(f"[Langfuse] Failed to fetch recent trace IDs: {e}")
        return []