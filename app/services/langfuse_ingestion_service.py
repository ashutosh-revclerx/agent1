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
from app.services.email_service import send_alert
from app.services.slack_service import send_slack_alert_text, slack_is_configured
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


# ── Alert Helpers ──────────────────────────────────────────────────────────────

def _derive_severity(health_score: int) -> str:
    """Convert a Langfuse health score (0-100) to a severity label."""
    if health_score < 50:
        return "CRITICAL"
    if health_score < 70:
        return "HIGH"
    if health_score < 85:
        return "MEDIUM"
    return "LOW"


def _get_app_user_ids_for_langfuse_users(langfuse_user_ids: list) -> list:
    """Map langfuse_user_ids → app user_ids via langfuse_watched_users.added_by."""
    db = get_db()
    if db is None or not langfuse_user_ids:
        return []
    try:
        docs = list(db.langfuse_watched_users.find(
            {"langfuse_user_id": {"$in": langfuse_user_ids}},
            {"added_by": 1, "_id": 0}
        ))
        # Deduplicate
        return list({d["added_by"] for d in docs if d.get("added_by")})
    except Exception as e:
        logger.error(f"[Langfuse RCA] Failed to resolve app user IDs: {e}")
        return []


def _send_langfuse_alerts(rca_doc: dict, langfuse_user_ids: list = None):
    """Send email + Slack alerts for a noteworthy Langfuse RCA result.

    Resolves which app users to notify via langfuse_watched_users,
    then calls send_alert() and send_slack_alert_text() per user.
    Falls back to a broadcast (no user_id) if no IDs resolved.
    """
    anomalies = rca_doc.get("anomalies", [])
    if not anomalies:
        return  # Nothing to alert on

    health = rca_doc.get("health_score", 100)
    severity = _derive_severity(health)
    summary = rca_doc.get("summary", "")
    root_cause = rca_doc.get("root_cause", "")
    total_errors = rca_doc.get("total_errors", 0)
    total_traces = rca_doc.get("total_traces", 0)
    total_cost = rca_doc.get("total_cost_usd", 0)
    recs = rca_doc.get("recommendations", [])
    immediate = [r["action"] for r in recs if isinstance(r, dict) and r.get("priority") == "immediate"]

    subject = f"[LANGFUSE {severity}] Anomaly Detected — Health: {health}/100"

    # Per-anomaly rows: Type | Severity | Affected Trace | Model | Msg/Code | Evidence
    anomaly_rows = "".join(
        f"<tr>"
        f"<td><b>{a.get('type', '')}</b></td>"
        f"<td style='color:{'red' if a.get('severity','') in ('high','critical') else 'orange'}'>{a.get('severity', '').upper()}</td>"
        f"<td><code>{a.get('affected_trace', '') or '—'}</code></td>"
        f"<td>{a.get('affected_model', '') or '—'}</td>"
        f"<td><code>{a.get('status_code', '') or 'N/A'}</code></td>"
        f"<td><small>{a.get('evidence', '') or '—'}</small></td>"
        f"</tr>"
        for a in anomalies[:10]
    )

    # Status code breakdown across all traces in this RCA window
    error_count = rca_doc.get("total_errors", 0)
    success_count = max(0, total_traces - error_count)
    status_rows = (
        f"<tr><td>✅ success</td><td>{success_count}</td></tr>"
        f"<tr><td>❌ error</td><td>{error_count}</td></tr>"
    )

    html = f"""<h2>🤖 [{severity}] Langfuse Anomaly Detected</h2>
<p>
  <b>Health Score:</b> {health}/100 &nbsp;|&nbsp;
  <b>Errors:</b> {total_errors}/{total_traces} traces &nbsp;|&nbsp;
  <b>Cost:</b> ${total_cost:.6f}
</p>
<p><b>Summary:</b> {summary}</p>
<p><b>Root Cause:</b> {root_cause}</p>

<h3>Trace Status Codes</h3>
<table border="1" cellpadding="4" style="border-collapse:collapse;">
  <tr><th>Status</th><th>Count</th></tr>
  {status_rows}
</table>

<h3>Anomalies ({len(anomalies)})</h3>
<table border="1" cellpadding="4" style="border-collapse:collapse;font-size:13px;">
  <tr>
    <th>Type</th><th>Severity</th><th>Affected Trace</th>
    <th>Model</th><th>Status Code</th><th>Evidence / Message</th>
  </tr>
  {anomaly_rows}
</table>

<p><b>Immediate Actions:</b></p>
<ul>{''.join(f'<li>{a}</li>' for a in immediate) or '<li>None</li>'}</ul>"""

    # Slack: include evidence of first anomaly
    first_evidence = anomalies[0].get("evidence", "") if anomalies else ""
    slack_msg = (
        f"🤖 *[LANGFUSE {severity}]* Anomaly Detected — Health: {health}/100\n"
        f"📋 {summary}\n"
        f"🔍 Root Cause: {root_cause}\n"
        f"💥 Status Codes: ✅ success={success_count} ❌ error={error_count} (of {total_traces} traces)\n"
        f"💰 Cost: ${total_cost:.6f}\n"
        f"🔎 Evidence: {first_evidence or 'see email for details'}\n"
        f"⚡ Actions: {', '.join(immediate) or 'None'}\n"
        f"📊 Anomalies: {len(anomalies)}"
    )


    # Resolve app user IDs to notify
    app_user_ids = _get_app_user_ids_for_langfuse_users(langfuse_user_ids or [])
    targets = app_user_ids if app_user_ids else [None]  # None = broadcast (env .env recipients)

    for app_user_id in targets:
        # Email
        success, reason = send_alert(subject, html, user_id=app_user_id)
        if success:
            logger.info(f"[Langfuse RCA] Email alert sent (user={app_user_id})")
        else:
            logger.warning(f"[Langfuse RCA] Email not sent (user={app_user_id}): {reason}")

        # Slack
        if slack_is_configured(user_id=app_user_id):
            ok = send_slack_alert_text(slack_msg, user_id=app_user_id)
            if ok:
                logger.info(f"[Langfuse RCA] Slack alert sent (user={app_user_id})")
            else:
                logger.warning(f"[Langfuse RCA] Slack alert failed (user={app_user_id})")


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


def _format_trace_lines(traces: list) -> str:
    """Format a list of trace dicts into readable lines for LLM prompts."""
    lines = [
        f"  - name={t.get('name', 'unknown')} | user={t.get('langfuse_user_id')} | "
        f"model={t.get('model')} | tokens={t.get('total_tokens', 0)} | "
        f"cost=${t.get('cost_usd', 0)} | latency={t.get('latency_s', '?')}s | "
        f"status={t.get('status')} | time={t.get('timestamp')}"
        for t in traces
    ]
    return chr(10).join(lines)


def _build_rca_prompt(traces: list, hours: int, label: str = None) -> str:
    """Build a prompt for full-window RCA analysis.
    label: optional context string shown in the prompt header (e.g. 'session abc-123')
    """
    context = label or f"the last {hours} hours" if hours else "this session"

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
You are running a full analysis on {len(traces)} traces from {context}.

TRACES TO EVALUATE:
{_format_trace_lines(traces)}

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
                "status_code": "string - actual error code or HTTP status if seen",
                "affected_model": "string",
                "affected_trace": "string",
                "evidence": "string - brief technical log snippet or error message",
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
{_format_trace_lines(new_traces)}

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

    # FIX BUG 1: Extract fields from analysis BEFORE using them
    noteworthy = analysis.get("noteworthy", False)
    health = analysis.get("health_score", 100)
    anomalies = analysis.get("anomalies", [])

    # Count real errors from the ingested traces (source of truth — not the LLM)
    actual_errors = sum(1 for t in new_traces if t.get("status") == "error")

    # Override LLM "not noteworthy" if there are real error traces
    if not noteworthy and health >= 95 and len(anomalies) == 0:
        if actual_errors == 0:
            logger.info(f"[Langfuse RCA] All normal (health={health}), skipping")
            return {}
        # Real errors detected — override LLM opinion, synthesize a minimal anomaly
        logger.info(
            f"[Langfuse RCA] LLM said normal but {actual_errors} error trace(s) found — overriding"
        )
        noteworthy = True
        health = min(health, 80)  # cap health score
        anomalies = [{
            "type": "error_spike",
            "severity": "high" if actual_errors > 1 else "medium",
            "description": f"{actual_errors} trace(s) with status=error detected",
            "affected_model": new_traces[0].get("model", "unknown"),
            "affected_trace": new_traces[0].get("name", "unknown"),
            "evidence": f"status=error in {actual_errors}/{len(new_traces)} new traces",
        }]
        analysis["anomalies"] = anomalies
        analysis["noteworthy"] = True
        analysis["health_score"] = health

    # Extract real user IDs from traces — used for storage and alerts
    involved_user_ids = list({t.get("langfuse_user_id") for t in new_traces if t.get("langfuse_user_id")})
    primary_user_id = involved_user_ids[0] if len(involved_user_ids) == 1 else None

    # Store batch RCA result
    rca_doc = {
        "timestamp": _utc_iso(),
        "window_hours": 0,
        "rca_type": "batch",                       # distinguishes from session/manual RCA
        "langfuse_user_id": primary_user_id,       # single user or None if multi-user batch
        "langfuse_user_ids": involved_user_ids,    # always populated for $or queries
        "total_traces": len(new_traces),
        "total_errors": actual_errors,             # reuse already-computed value
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

    # Send email + Slack alerts — reuse involved_user_ids already computed above
    _send_langfuse_alerts(rca_doc, langfuse_user_ids=involved_user_ids)

    # Auto-store sessions that have error traces only
    # Group error traces by session_id and store each errored session
    error_traces = [t for t in new_traces if t.get("status") == "error"]
    if error_traces:
        _store_errored_sessions(db, error_traces, rca_doc)

    rca_doc.pop("_id", None)
    return rca_doc


def _store_errored_sessions(db, error_traces: list, rca_doc: dict):
    """
    Auto-store sessions that contain error traces.
    Called automatically after RCA when errors are detected.
    Groups error traces by session_id and upserts one document
    per session into langfuse_stored_sessions.
    Traces with no session_id are stored using trace_id as the key.
    """
    # Group error traces by session_id (or trace_id if no session)
    session_map = {}
    for t in error_traces:
        key = t.get("session_id") or t.get("trace_id")
        if key not in session_map:
            session_map[key] = []
        session_map[key].append(t)

    for session_key, errored in session_map.items():
        user_ids = list({t.get("langfuse_user_id") for t in errored if t.get("langfuse_user_id")})
        is_sessionless = not errored[0].get("session_id")

        # Fetch all traces for this session (not just errored ones) for full context
        if not is_sessionless:
            all_session_traces = list(db.langfuse_traces.find(
                {"session_id": session_key}, {"_id": 0}
            ))
        else:
            # No session — use just the errored trace
            all_session_traces = errored

        latencies = [t["latency_s"] for t in all_session_traces if t.get("latency_s")]
        metrics = {
            "total_traces": len(all_session_traces),
            "total_tokens": sum(t.get("total_tokens", 0) for t in all_session_traces),
            "total_cost_usd": round(sum(t.get("cost_usd", 0) for t in all_session_traces), 6),
            "avg_latency_s": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
            "error_count": sum(1 for t in all_session_traces if t.get("status") == "error"),
            "models_used": list({t.get("model") for t in all_session_traces if t.get("model")}),
        }

        # Run a dedicated RCA on the FULL session context
        # This is more accurate than the batch RCA that ran on all new traces
        session_rca = {}
        try:
            session_prompt = _build_rca_prompt(
                all_session_traces,
                hours=0,
                label=f"session {session_key}"
            )
            session_id_str = f"session-rca-{uuid.uuid4().hex[:8]}"
            result = ask_llm(session_prompt, "Session RCA", {
                "session_id": session_key,
                "trace_count": len(all_session_traces),
                "error_count": metrics["error_count"],
            }, session_id=session_id_str)

            if result:
                text, _ = result
                session_rca = parse_json(text) if text else {}
                logger.info(
                    f"[Langfuse RCA] Session RCA complete: "
                    f"session={session_key} health={session_rca.get('health_score', '?')}"
                )
            else:
                logger.warning(f"[Langfuse RCA] Session RCA returned no result for {session_key}")
        except Exception as e:
            logger.error(f"[Langfuse RCA] Session RCA failed for {session_key}: {e}")

        # Store the session-level RCA separately in langfuse_rca
        if session_rca:
            session_rca_doc = {
                "timestamp": _utc_iso(),
                "window_hours": 0,
                "session_id": session_key,
                "langfuse_user_id": user_ids[0] if len(user_ids) == 1 else None,
                "langfuse_user_ids": user_ids,
                "total_traces": len(all_session_traces),
                "total_errors": metrics["error_count"],
                "total_cost_usd": metrics["total_cost_usd"],
                "summary": session_rca.get("summary", ""),
                "root_cause": session_rca.get("root_cause", ""),
                "anomalies": session_rca.get("anomalies", []),
                "recommendations": session_rca.get("recommendations", []),
                "health_score": session_rca.get("health_score", 100),
                "raw_analysis": session_rca,
                "rca_type": "session",   # distinguishes from batch RCA
            }
            try:
                db.langfuse_rca.insert_one(session_rca_doc)
                session_rca_doc.pop("_id", None)
                session_rca_doc.pop("raw_analysis", None)
            except Exception as e:
                logger.error(f"[Langfuse RCA] Failed to store session RCA for {session_key}: {e}")

        # Safely resolve which RCA to attach — session-level if available, batch as fallback
        # session_rca_doc is only defined inside the `if session_rca:` block above,
        # so we use locals().get() to avoid NameError when session RCA failed
        resolved_rca = locals().get("session_rca_doc") or {
            k: v for k, v in rca_doc.items()
            if k not in ("_id", "raw_analysis")
        }

        doc = {
            "session_id": session_key,
            "is_sessionless": is_sessionless,
            "stored_at": _utc_iso(),
            "auto_stored": True,
            "langfuse_user_ids": user_ids,
            "metrics": metrics,
            "traces": all_session_traces,
            "latest_rca": resolved_rca,
        }

        try:
            db.langfuse_stored_sessions.replace_one(
                {"session_id": session_key},
                doc,
                upsert=True,
            )
            logger.info(
                f"[Langfuse RCA] Auto-stored errored session: "
                f"session={session_key} errors={metrics['error_count']} "
                f"sessionless={is_sessionless}"
            )
        except Exception as e:
            logger.error(f"[Langfuse RCA] Failed to store errored session {session_key}: {e}")


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
        "rca_type": "manual",
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

    # Send email + Slack alerts for noteworthy anomalies
    if langfuse_user_id:
        _send_langfuse_alerts(rca_doc, langfuse_user_ids=[langfuse_user_id])
    else:
        _send_langfuse_alerts(rca_doc, langfuse_user_ids=[])

    rca_doc.pop("_id", None)
    return rca_doc


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