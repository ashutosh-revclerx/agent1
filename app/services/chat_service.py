"""
Chat Service
Provides context retrieval and LLM querying for external chatbot interfaces (e.g., LibreChat).
Enables querying about specific Monitoring or Langfuse sessions.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from app.services.mongodb_service import get_db
from app.services.llm_service import ask_llm
from app.core.logging import logger

class ChatService:
    def __init__(self):
        pass

    def list_recent_sessions(self, db, limit: int = 5) -> Dict[str, List[Dict[str, Any]]]:
        """List the most recent monitoring and langfuse sessions."""
        monitoring = list(db.metrics_batches.find({}, {"session_id": 1, "window_start": 1, "incident_id": 1, "_id": 0})
                          .sort("window_start", -1).limit(limit))
        
        langfuse = list(db.langfuse_stored_sessions.find({}, {"session_id": 1, "timestamp": 1, "metrics": 1, "_id": 0})
                         .sort("timestamp", -1).limit(limit))
        
        return {
            "monitoring": monitoring,
            "langfuse": langfuse
        }

    def get_monitoring_context(self, db, session_id: str) -> Dict[str, Any]:
        """Fetch all metrics, anomalies, and RCAs related to a monitoring session/window."""
        # A monitoring "session_id" usually refers to the window-based session_id in metrics_batches
        batch = db.metrics_batches.find_one({"session_id": session_id})
        if not batch:
            # Try finding via incident_id if session_id is actually an incident reference
            batch = db.metrics_batches.find_one({"incident_id": session_id})
            
        if not batch:
            return {}

        window_start = batch.get("window_start")
        window_end = batch.get("window_end")
        user_id = batch.get("user_id")

        # Gather related data
        anomalies = list(db.anomalies.find({"session_id": session_id}, {"_id": 0}))
        incident = db.incidents.find_one({"session_id": session_id}, {"_id": 0})
        rca = db.rca.find_one({"session_id": session_id}, {"_id": 0})
        
        # If no rca for this session, check if there's rca for the same window
        if not rca and window_start:
             rca = db.rca.find_one({"window_start": window_start, "user_id": user_id}, {"_id": 0})

        return {
            "type": "monitoring",
            "session_id": session_id,
            "window": f"{window_start} to {window_end}" if window_start else "unknown",
            "metrics_summary": {
                "count": len(batch.get("metrics", [])),
                "ip": batch.get("ip")
            },
            "anomalies": anomalies,
            "incident": incident,
            "rca": rca,
            "raw_metrics": batch.get("metrics", [])[:20] # Limit to avoid token blowup
        }

    def get_langfuse_context(self, db, session_id: str) -> Dict[str, Any]:
        """Fetch traces and RCA for a Langfuse session."""
        # Check stored sessions first (richer data)
        stored = db.langfuse_stored_sessions.find_one({"session_id": session_id}, {"_id": 0})
        if stored:
            return {
                "type": "langfuse",
                "session_id": session_id,
                "metrics": stored.get("metrics"),
                "traces": stored.get("traces", [])[:10], # Latest traces
                "rca": stored.get("latest_rca")
            }

        # Fallback: query raw traces
        traces = list(db.langfuse_traces.find({"session_id": session_id}, {"_id": 0}).sort("timestamp", -1).limit(20))
        if not traces:
            return {}

        # Find latest RCA for this user or session
        user_id = traces[0].get("langfuse_user_id")
        rca = db.langfuse_rca.find_one(
            {"$or": [{"session_id": session_id}, {"langfuse_user_id": user_id}]},
            {"_id": 0},
            sort=[("timestamp", -1)]
        )

        return {
            "type": "langfuse",
            "session_id": session_id,
            "traces": traces,
            "rca": rca
        }

    def format_context_for_llm(self, context: Dict[str, Any]) -> str:
        """Convert context dictionary to a structured prompt string."""
        if not context:
            return "No specific system context found for this session."

        lines = [f"SYSTEM CONTEXT ({context.get('type', 'unknown').upper()}):"]
        lines.append(f"Session ID: {context.get('session_id')}")
        
        if context["type"] == "monitoring":
            lines.append(f"Time Window: {context.get('window')}")
            inc = context.get("incident") or {}
            lines.append(f"Incident: {inc.get('title', 'None')} (Severity: {inc.get('severity', 'N/A')})")
            lines.append(f"Summary: {inc.get('summary', 'N/A')}")
            
            rca = context.get("rca") or {}
            lines.append(f"Root Cause Analysis: {rca.get('root_cause', rca.get('analysis', 'Not analyzed'))}")
            
            anomalies = context.get("anomalies", [])
            if anomalies:
                lines.append("Detected Anomalies:")
                for a in anomalies[:5]:
                    lines.append(f" - [{a.get('type')}] {a.get('description')} (Sev: {a.get('severity')})")
        
        elif context["type"] == "langfuse":
            metrics = context.get("metrics") or {}
            if metrics:
                lines.append(f"Stats: {metrics.get('error_count')} errors in {metrics.get('total_traces')} traces.")
            
            rca = context.get("rca") or {}
            lines.append(f"RCA Summary: {rca.get('summary', 'N/A')}")
            lines.append(f"Root Cause: {rca.get('root_cause', 'N/A')}")
            
            traces = context.get("traces", [])
            if traces:
                lines.append("Recent Traces:")
                for t in traces[:5]:
                    status = "❌" if t.get("status") == "error" else "✅"
                    lines.append(f" - {status} {t.get('name')} | Model: {t.get('model')} | Latency: {t.get('latency_s')}s")

        return "\n".join(lines)

    async def query_session(self, session_id: str, context_type: str, user_id: str, message: str) -> Optional[str]:
        """Main entry point for chatbot queries."""
        db = get_db()
        if db is None:
            return "Error: Database unavailable."

        context_data = {}
        if context_type == "monitoring":
            context_data = self.get_monitoring_context(db, session_id)
        elif context_type == "langfuse":
            context_data = self.get_langfuse_context(db, session_id)
        
        context_str = self.format_context_for_llm(context_data)
        
        prompt = f"""You are a Devops & LLM Operations assistant.
The user is asking a question about a specific session in the monitoring system.

{context_str}

USER MESSAGE: {message}

INSTRUCTIONS:
1. Use the system context above to provide an accurate, helpful answer.
2. If the context contains an RCA (Root Cause Analysis), explain it to the user.
3. If the user asks about errors, refer to the traces or anomalies.
4. If the context is missing, explain what you would need to investigate.
5. Keep your tone professional and technical.

RESPONSE:"""

        result = ask_llm(prompt, trace_name="Chatbot Query", user_id=user_id, metadata={
            "session_id": session_id,
            "context_type": context_type
        })
        
        if result:
            return result[0]
        return "I encountered an error while processing your request."

chat_service = ChatService()
