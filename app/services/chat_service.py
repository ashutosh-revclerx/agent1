"""
Chat Service
Provides context retrieval and LLM querying for external chatbot interfaces (e.g., LibreChat).
Enables querying about specific Monitoring or Langfuse sessions, or the most recent data.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from app.services.mongodb_service import get_db
from app.services.llm_service import ask_llm
from app.core.logging import logger


def _safe_str(val) -> str:
    """Convert any value to string safely."""
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


class ChatService:
    def __init__(self):
        pass

    # ─── Session Listing ────────────────────────────────────────────────────────

    def list_recent_sessions(self, db, limit: int = 5) -> Dict[str, Any]:
        """List the most recent monitoring and langfuse sessions with rich metadata."""
        if db is None:
            return {"monitoring": [], "langfuse": [], "error": "Database unavailable"}

        # Monitoring: pull from incidents (richer: has severity, title, ip:port)
        incident_docs = list(
            db.incidents.find(
                {},
                {
                    "langfuse_session_id": 1, "window_start_ist_str": 1,
                    "window_end_ist_str": 1, "ip": 1, "port": 1,
                    "severity": 1, "title": 1, "confidence": 1, "user_id": 1,
                    "_id": 0
                }
            ).sort([("window_start_ist_str", -1), ("_id", -1)]).limit(limit)
        )

        monitoring = []
        for doc in incident_docs:
            session_id = doc.get("langfuse_session_id")
            ip = doc.get("ip", "")
            port = doc.get("port", "")
            target = f"{ip}:{port}" if port else ip or "unknown"

            # Count anomalies for this session
            anomaly_count = 0
            if session_id:
                try:
                    anomaly_count = db.anomalies.count_documents({"langfuse_session_id": session_id})
                except Exception:
                    pass

            monitoring.append({
                "session_id": session_id or "",
                "window_start": _safe_str(doc.get("window_start_ist_str")),
                "window_end": _safe_str(doc.get("window_end_ist_str")),
                "target": target,
                "severity": doc.get("severity", "unknown"),
                "title": doc.get("title", "Batch Analysis"),
                "confidence": doc.get("confidence"),
                "anomaly_count": anomaly_count,
                "user_id": doc.get("user_id"),
            })

        # Langfuse: pull from stored sessions (error sessions only) + raw RCA
        lf_stored = list(
            db.langfuse_stored_sessions.find(
                {},
                {
                    "session_id": 1, "stored_at": 1, "metrics": 1,
                    "langfuse_user_ids": 1, "latest_rca": 1, "_id": 0
                }
            ).sort("stored_at", -1).limit(limit)
        )

        langfuse = []
        for doc in lf_stored:
            metrics = doc.get("metrics") or {}
            rca = doc.get("latest_rca") or {}
            langfuse.append({
                "session_id": doc.get("session_id"),
                "stored_at": _safe_str(doc.get("stored_at")),
                "error_count": metrics.get("error_count", 0),
                "total_traces": metrics.get("total_traces", 0),
                "total_cost_usd": metrics.get("total_cost_usd", 0),
                "health_score": rca.get("health_score"),
                "rca_summary": rca.get("summary", ""),
                "langfuse_user_ids": doc.get("langfuse_user_ids", []),
            })

        # If no stored sessions, fall back to batch RCA list
        if not langfuse:
            rca_docs = list(
                db.langfuse_rca.find(
                    {},
                    {
                        "timestamp": 1, "langfuse_user_id": 1, "rca_type": 1,
                        "health_score": 1, "summary": 1, "total_errors": 1,
                        "total_traces": 1, "_id": 0
                    }
                ).sort("timestamp", -1).limit(limit)
            )
            for doc in rca_docs:
                langfuse.append({
                    "session_id": doc.get("langfuse_user_id", "—"),
                    "stored_at": _safe_str(doc.get("timestamp")),
                    "error_count": doc.get("total_errors", 0),
                    "total_traces": doc.get("total_traces", 0),
                    "health_score": doc.get("health_score"),
                    "rca_summary": doc.get("summary", ""),
                    "rca_type": doc.get("rca_type", "batch"),
                })

        return {"monitoring": monitoring, "langfuse": langfuse}

    # ─── Latest Data (no session ID needed) ─────────────────────────────────────

    def get_latest_snapshot(self, db) -> Dict[str, Any]:
        """
        Return the most recent monitoring incident + Langfuse RCA and traces — 
        no session_id required. Ideal for 'give me a health summary' queries.
        """
        if db is None:
            return {}

        # Latest monitoring incident
        incident = db.incidents.find_one(
            {}, {"_id": 0}, sort=[("window_start_ist_str", -1)]
        )
        if incident:
            session_id = incident.get("langfuse_session_id")
            anomalies = []
            if session_id:
                anomalies = list(
                    db.anomalies.find({"langfuse_session_id": session_id}, {"_id": 0}).limit(10)
                )
            rca = db.rca.find_one(
                {"langfuse_session_id": session_id} if session_id else {}, {"_id": 0},
                sort=[("created_at_ist", -1)]
            )
        else:
            anomalies = []
            rca = None

        # Latest Langfuse RCA
        lf_rca = db.langfuse_rca.find_one(
            {}, {"_id": 0, "raw_analysis": 0}, sort=[("timestamp", -1)]
        )

        # Recent Langfuse traces (last 10)
        lf_traces = list(
            db.langfuse_traces.find({}, {"_id": 0}).sort("timestamp", -1).limit(10)
        )

        return {
            "monitoring": {
                "incident": incident,
                "anomalies": anomalies,
                "rca": rca,
            },
            "langfuse": {
                "rca": lf_rca,
                "recent_traces": lf_traces,
            }
        }

    # ─── Session Context ─────────────────────────────────────────────────────────

    def get_monitoring_context(self, db, session_id: str) -> Dict[str, Any]:
        """Fetch all metrics, anomalies, and RCAs related to a monitoring session."""
        batch = db.metrics_batches.find_one({"langfuse_session_id": session_id})
        if not batch:
            # Try by batch _id if session_id wasn't found
            incident = db.incidents.find_one({"langfuse_session_id": session_id}, {"_id": 0})
            if not incident:
                return {}
            batch = db.metrics_batches.find_one({"user_id": incident.get("user_id")},
                                                 sort=[("window_start_ist", -1)])
        if not batch:
            return {}

        window_start = batch.get("window_start_ist")
        window_end = batch.get("window_end_ist")
        user_id = batch.get("user_id")
        window_start_str = batch.get("window_start_ist_str", _safe_str(window_start))
        window_end_str = batch.get("window_end_ist_str", _safe_str(window_end))

        anomalies = list(db.anomalies.find({"langfuse_session_id": session_id}, {"_id": 0}))
        incident = db.incidents.find_one({"langfuse_session_id": session_id}, {"_id": 0})
        rca = db.rca.find_one({"langfuse_session_id": session_id}, {"_id": 0})

        if not rca and window_start:
            query = {"window_start_ist": window_start}
            if user_id:
                query["user_id"] = user_id
            rca = db.rca.find_one(query, {"_id": 0})

        ip = batch.get("ip") or (incident.get("ip") if incident else "")
        port = batch.get("port") or (incident.get("port") if incident else "")

        return {
            "type": "monitoring",
            "session_id": session_id,
            "window": f"{window_start_str} → {window_end_str}",
            "target": f"{ip}:{port}" if port else ip or "unknown",
            "metrics_count": len(batch.get("metrics", [])),
            "anomaly_count": len(anomalies),
            "anomalies": anomalies[:10],
            "incident": incident,
            "rca": rca,
            "raw_metrics": batch.get("metrics", [])[:15],  # capped for token efficiency
        }

    def get_langfuse_context(self, db, session_id: str) -> Dict[str, Any]:
        """Fetch traces and RCA for a Langfuse session."""
        stored = db.langfuse_stored_sessions.find_one({"session_id": session_id}, {"_id": 0})
        if stored:
            return {
                "type": "langfuse",
                "session_id": session_id,
                "metrics": stored.get("metrics"),
                "traces": stored.get("traces", [])[:10],
                "rca": stored.get("latest_rca"),
                "langfuse_user_ids": stored.get("langfuse_user_ids", []),
            }

        # Fallback: query raw user traces
        traces = list(
            db.langfuse_traces.find(
                {"langfuse_user_id": session_id}, {"_id": 0}
            ).sort("timestamp", -1).limit(20)
        )
        if not traces:
            # Try by session_id field
            traces = list(
                db.langfuse_traces.find({"session_id": session_id}, {"_id": 0}).sort("timestamp", -1).limit(20)
            )
        if not traces:
            return {}

        user_id = traces[0].get("langfuse_user_id")
        rca = db.langfuse_rca.find_one(
            {"$or": [{"session_id": session_id}, {"langfuse_user_id": user_id}]},
            {"_id": 0, "raw_analysis": 0},
            sort=[("timestamp", -1)]
        )

        error_count = sum(1 for t in traces if t.get("status") == "error")
        return {
            "type": "langfuse",
            "session_id": session_id,
            "error_count": error_count,
            "total_traces": len(traces),
            "traces": traces[:10],
            "rca": rca,
        }

    # ─── Context Formatting ───────────────────────────────────────────────────────

    def format_context_for_llm(self, context: Dict[str, Any]) -> str:
        """Convert context dict to a structured, token-efficient prompt block."""
        if not context:
            return "No specific system context found."

        lines = [f"=== SYSTEM CONTEXT ({context.get('type', 'unknown').upper()}) ==="]

        ctx_type = context.get("type")

        if ctx_type == "monitoring":
            lines.append(f"Session: {context.get('session_id')}")
            lines.append(f"Window: {context.get('window')}")
            lines.append(f"Target: {context.get('target')}")
            lines.append(f"Metrics collected: {context.get('metrics_count')} | Anomalies: {context.get('anomaly_count', 0)}")

            inc = context.get("incident") or {}
            if inc:
                lines.append(f"\nINCIDENT: [{inc.get('severity', '?').upper()}] {inc.get('title', 'N/A')}")
                lines.append(f"Summary: {inc.get('summary', 'N/A')}")
                lines.append(f"Confidence: {inc.get('confidence', '?')}")
                lines.append(f"Root Cause: {inc.get('root_cause', 'N/A')}")

                fix = inc.get("fix_plan", {})
                if isinstance(fix, dict):
                    immediate = fix.get("immediate", [])
                    if immediate:
                        lines.append(f"Immediate actions: {'; '.join(str(a) for a in immediate[:3])}")

            rca = context.get("rca") or {}
            if rca:
                rca_text = rca.get("cause") or rca.get("root_cause") or rca.get("analysis", "Not analyzed")
                lines.append(f"\nRCA Cause: {rca_text}")
                fix = rca.get("fix")
                if fix:
                    lines.append(f"RCA Fix: {fix if isinstance(fix, str) else '; '.join(str(f) for f in fix[:3])}")

            anomalies = context.get("anomalies", [])
            if anomalies:
                lines.append(f"\nTOP ANOMALIES ({len(anomalies)}):")
                for a in anomalies[:8]:
                    lines.append(
                        f"  [{a.get('metric')}] obs={a.get('observed')} expected={a.get('expected')} "
                        f"on {a.get('instance')} — {a.get('symptom', '')}"
                    )

            metrics = context.get("raw_metrics", [])
            if metrics:
                lines.append(f"\nSAMPLE METRICS ({len(metrics)} shown):")
                for m in metrics[:10]:
                    lines.append(f"  {m.get('name')}: {m.get('value')} [{m.get('instance')}]")

        elif ctx_type == "langfuse":
            lines.append(f"Session: {context.get('session_id')}")
            metrics = context.get("metrics") or {}
            if metrics:
                lines.append(
                    f"Error rate: {metrics.get('error_count', 0)}/{metrics.get('total_traces', 0)} traces | "
                    f"Cost: ${metrics.get('total_cost_usd', 0)} | "
                    f"Avg latency: {metrics.get('avg_latency_s', 0)}s"
                )
            else:
                lines.append(
                    f"Errors: {context.get('error_count', 0)}/{context.get('total_traces', 0)} traces"
                )

            rca = context.get("rca") or {}
            if rca:
                lines.append(f"\nRCA Summary: {rca.get('summary', 'N/A')}")
                lines.append(f"Root Cause: {rca.get('root_cause', 'N/A')}")
                lines.append(f"Health Score: {rca.get('health_score', '?')}/100")
                recs = rca.get("recommendations", [])
                if recs:
                    lines.append("Recommendations:")
                    for r in recs[:3]:
                        lines.append(f"  [{r.get('priority','?')}] {r.get('action','')}")
                anomalies = rca.get("anomalies", [])
                if anomalies:
                    lines.append(f"Anomalies detected: {len(anomalies)}")
                    for a in anomalies[:4]:
                        lines.append(f"  [{a.get('type','')}:{a.get('severity','')}] {a.get('description','')}")

            traces = context.get("traces", [])
            if traces:
                lines.append(f"\nRECENT TRACES ({len(traces)}):")
                for t in traces[:8]:
                    status = "ERR" if t.get("status") == "error" else "OK"
                    lines.append(
                        f"  [{status}] {t.get('name','?')} | {t.get('model','?')} | "
                        f"lat={t.get('latency_s','?')}s | tokens={t.get('total_tokens',0)}"
                    )

        return "\n".join(lines)

    def format_snapshot_for_llm(self, snapshot: Dict[str, Any]) -> str:
        """Format the latest snapshot (no session ID) into a concise prompt block."""
        if not snapshot:
            return "No recent data found in the system."

        lines = ["=== LATEST SYSTEM SNAPSHOT ==="]

        mon = snapshot.get("monitoring", {})
        inc = mon.get("incident") or {}
        if inc:
            lines.append(f"\n[MONITORING] Latest incident: [{inc.get('severity','?').upper()}] {inc.get('title','N/A')}")
            lines.append(f"Window: {inc.get('window_start_ist_str','?')} → {inc.get('window_end_ist_str','?')}")
            lines.append(f"Root Cause: {inc.get('root_cause', inc.get('summary', 'N/A'))}")
        else:
            lines.append("\n[MONITORING] No recent incidents found.")

        anomalies = mon.get("anomalies", [])
        if anomalies:
            lines.append(f"Anomalies ({len(anomalies)} in last batch):")
            for a in anomalies[:5]:
                lines.append(f"  [{a.get('metric')}] {a.get('symptom','')}")

        lf = snapshot.get("langfuse", {})
        lf_rca = lf.get("rca") or {}
        if lf_rca:
            lines.append(
                f"\n[LANGFUSE] Health: {lf_rca.get('health_score','?')}/100 | "
                f"Summary: {lf_rca.get('summary','N/A')}"
            )
        else:
            lines.append("\n[LANGFUSE] No recent RCA found.")

        traces = lf.get("recent_traces", [])
        if traces:
            errors = sum(1 for t in traces if t.get("status") == "error")
            lines.append(f"Last {len(traces)} traces: {errors} errors")

        return "\n".join(lines)

    # ─── Main Entry Points ────────────────────────────────────────────────────────

    async def query_session(self, session_id: str, context_type: str, user_id: str, message: str) -> Optional[str]:
        """Query about a specific session."""
        db = get_db()
        if db is None:
            return "Error: Database unavailable."

        context_data = {}
        if context_type == "monitoring":
            context_data = self.get_monitoring_context(db, session_id)
        elif context_type == "langfuse":
            context_data = self.get_langfuse_context(db, session_id)

        context_str = self.format_context_for_llm(context_data)

        prompt = f"""You are an expert DevOps & LLM Operations assistant embedded in an AI monitoring system.
The user is asking a question about a specific session in the monitoring system.

{context_str}

USER QUESTION: {message}

INSTRUCTIONS:
1. Answer the question using ONLY the system context above.
2. Highlight severity, root causes, and recommended actions where relevant.
3. If anomalies are listed, explain the most critical ones.
4. If the context is missing or sparse, tell the user what data would be needed.
5. Be concise, accurate, and technical. Format clearly.

RESPONSE:"""

        result = ask_llm(prompt, trace_name="LibreChat Session Query", user_id=user_id, metadata={
            "session_id": session_id,
            "context_type": context_type
        })

        return result[0] if result else "I encountered an error while processing your request."

    async def query_latest(self, user_id: str, message: str) -> Optional[str]:
        """Query about the latest system state without needing a session ID."""
        db = get_db()
        if db is None:
            return "Error: Database unavailable."

        snapshot = self.get_latest_snapshot(db)
        context_str = self.format_snapshot_for_llm(snapshot)

        prompt = f"""You are an expert DevOps & LLM Operations assistant embedded in an AI monitoring system.
The user wants a health summary or is asking a general question about the system's current state.

{context_str}

USER QUESTION: {message}

INSTRUCTIONS:
1. Provide a clear, concise health summary based on the snapshot above.
2. Call out any critical incidents or high-severity anomalies.
3. Comment on the LLM trace health (Langfuse).
4. Suggest next actions if problems are detected.
5. Keep it focused — max 5-6 sentences unless asked for more detail.

RESPONSE:"""

        result = ask_llm(prompt, trace_name="LibreChat Latest Query", user_id=user_id, metadata={
            "query_type": "latest_snapshot"
        })

        return result[0] if result else "I encountered an error while processing your request."


chat_service = ChatService()
