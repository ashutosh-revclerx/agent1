import asyncio
import os
import json
import uvicorn
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timedelta
from pymongo import UpdateOne

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi.errors import RateLimitExceeded

from app.core.config import PROM_URL, BATCH_INTERVAL_MINUTES, MONGO_URI
from app.core.logging import logger
from app.core.time import now_ist, ist_to_utc, format_ist
from app.core.helpers import parse_json
from app.core.rate_limit import limiter, rate_limit_exceeded_handler

from app.services.langfuse_service import (
    initialize_langfuse, is_langfuse_enabled,
    get_langfuse_client, make_batch_session_id, make_batch_window
)
from app.services.slack_service import send_slack_alert_text, slack_is_configured
from app.services.email_service import send_alert

# ✅ updated: use db.py helpers
from app.services.mongodb_service import get_db, parse_instance, build_source, looks_like_instance

from app.services.prometheus_service import fetch_metrics
from app.services.llm_service import ask_llm
from app.services.session_service import session_manager

from app.api.router import api_router
from app.services.langfuse_ingestion_service import poll_langfuse

try:
    from langfuse import propagate_attributes
except (ImportError, AttributeError):
    propagate_attributes = None

from app.core.firebase import initialize_firebase
initialize_firebase()


from app.services.monitoring_service import monitor_manager


def _migrate_alert_windows_for_tenant_scoping(db) -> None:
    coll = db.alert_windows
    legacy_filters = {
        "$or": [
            {"user_id": {"$exists": False}},
            {"user_id": None},
            {"user_id": ""},
        ]
    }
    legacy_docs = list(coll.find(legacy_filters, {"_id": 1}))
    if legacy_docs:
        coll.bulk_write(
            [
                UpdateOne(
                    {"_id": doc["_id"]},
                    {"$set": {"user_id": f"__legacy__:{doc['_id']}"}},
                )
                for doc in legacy_docs
            ]
        )
        logger.warning(
            f"[Database] Migrated {len(legacy_docs)} legacy alert_windows "
            "documents to synthetic tenant ids"
        )

            logger.info(f"[Batch] Stored: batch={batch_id}, incident={incident_id}, anomalies={len(anomalies)}")

        except Exception as e:
            logger.error(f"[Batch] Storage error: {e}", exc_info=True)

        return batch_id, incident_id

    def send_alerts(self, incident: Dict, anomalies: List, start: datetime, end: datetime, session_id: str):
        """Send Slack and Email alerts with IST times."""
        sev = incident.get("severity", "low").upper()
        title = incident.get("title", "Batch Analysis")
        window = f"{start.strftime('%Y-%m-%d %H:%M')} -> {end.strftime('%H:%M')} IST"
        immediate = incident.get("fix_plan", {}).get("immediate", [])

        if slack_is_configured():
            msg = f"""🚨 [{sev}] {title}
📅 Window: {window}
📋 {incident.get('summary', '')}
🔍 Root Cause: {incident.get('root_cause', 'Unknown')}
💥 Blast Radius: {incident.get('blast_radius', 'Unknown')}
⚡ Actions: {', '.join(immediate) or 'None'}
📊 Anomalies: {len(anomalies)}
🔗 Session: {session_id}"""
            try:
                send_slack_alert_text(msg, user_id=self.user_id)
            except Exception as e:
                logger.error(f"[Alerts] Slack error: {e}")

        try:
            html = f"""<h2>🚨 [{sev}] {title}</h2>
<p><b>Window:</b> {window}</p>
<p><b>Summary:</b> {incident.get('summary', '')}</p>
<p><b>Root Cause:</b> {incident.get('root_cause', '')}</p>
<p><b>Blast Radius:</b> {incident.get('blast_radius', '')}</p>
<p><b>Immediate Actions:</b></p><ul>{''.join(f'<li>{a}</li>' for a in immediate) or '<li>None</li>'}</ul>
<p><b>Anomalies:</b> {len(anomalies)} | <b>Confidence:</b> {incident.get('confidence', 0):.0%}</p>"""
            send_alert(f"[{sev}] {title}", html, user_id=self.user_id)
        except Exception as e:
            logger.error(f"[Alerts] Email error: {e}")

    async def run_worker(self):
        start, end = self.get_window()
        session_id = self.get_session_id(start)
        window_str = f"{start.strftime('%H:%M')}->{end.strftime('%H:%M')} IST"

        user_log = f" [User: {self.user_id}]" if self.user_id else ""
        logger.info(f"[Batch]{user_log} Running: {window_str} | Session: {session_id}")

        db = get_db()
        if self.is_processed(db, start, end):
            logger.info(f"[Batch]{user_log} Already processed - skipping")
            return

        langfuse = get_langfuse_client()
        span_ctx = prop_ctx = None

        if langfuse and is_langfuse_enabled():
            try:
                span_ctx = langfuse.start_as_current_observation(
                    as_type="span", name="Batch Monitoring",
                    metadata={
                        "window_start": start.isoformat(),
                        "window_end": end.isoformat(),
                        "timezone": "IST",
                        "user_id": self.user_id
                    }
                )
                span_ctx.__enter__()
                if propagate_attributes:
                    prop_ctx = propagate_attributes(session_id=session_id)
                    prop_ctx.__enter__()
            except Exception as e:
                logger.warning(f"[Langfuse] Span error: {e}")

        try:
            # Fetch metrics for this specific user only
            if self.user_id:
                from app.services.prometheus_service import fetch_metrics_for_user
                metrics = await fetch_metrics_for_user(self.user_id)
            else:
                # Fallback to all metrics if no user_id (backward compatibility)
                metrics = await fetch_metrics()
            
            if not metrics:
                logger.warning(f"[Batch]{user_log} No metrics - skipping")
                return

            logger.info(f"[Batch]{user_log} Fetched {len(metrics)} metrics")

            # LLM metadata (Gemini primary, OpenAI/Gemma3 fallback)
            llm_metadata = {
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
                "metrics_count": len(metrics),
                "timezone": "IST",
                "user_id": self.user_id,
                "llm_provider": "gemini",
                "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
                "google_api_key_set": bool(os.getenv("GOOGLE_API_KEY", "").strip()),
            }

            analysis = await self.call_llm(
                self.build_prompt(metrics, start, end),
                session_id,
                llm_metadata
            )

            if not analysis:
                logger.error(f"[Batch]{user_log} LLM analysis failed")
                return

            incident = analysis.get("incident", {}) or {}
            anomalies = analysis.get("anomalies", []) or []

            logger.info(
                f"[Batch]{user_log} Result: {incident.get('title')} | {incident.get('severity')} | {len(anomalies)} anomalies"
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("[Startup] AI DevOps Monitor v2.0")
    logger.info("[Config] Timezone: IST (UTC+5:30)")
    logger.info(f"[Config] Current Time: {format_ist(now_ist())}")
    logger.info(f"[Config] Prometheus: {PROM_URL or 'NOT SET'}")
    
    # LLM Configuration Logging
    logger.info(f"[Config] LLM Provider: Gemini (Primary)")
    logger.info(f"[Config] GEMINI_MODEL: {os.getenv('GEMINI_MODEL', 'gemini-2.0-flash')}")
    logger.info(f"[Config] GOOGLE_API_KEY: {'✅ Set' if (os.getenv('GOOGLE_API_KEY') or '').strip() else '❌ NOT SET'}")
    logger.info(f"[Config] Fallback: Gemma3 (Local)")
    
    logger.info(f"[Config] MongoDB: {MONGO_URI[:30] if MONGO_URI else 'NOT SET'}...")
    logger.info(f"[Config] Batch Interval: {BATCH_INTERVAL_MINUTES} min")

    initialize_langfuse()
    logger.info(f"[Langfuse] {'✅ Enabled' if is_langfuse_enabled() else '❌ Disabled'}")
    logger.info(f"[Slack] {'✅ Enabled' if slack_is_configured() else '❌ Disabled'}") 

    db = get_db()
    if db is not None:
        try:
            # Create users collection indexes
            db.users.create_index("username", unique=True)
            db.users.create_index("email", unique=True)
            
            # Create sessions collection indexes
            db.sessions.create_index("session_id", unique=True)
            db.sessions.create_index([("user_id", 1), ("active", 1)])
            db.sessions.create_index("last_active")
            
            # indexes
            db.chat_sessions.create_index("session_id", unique=True)
            db.chat_sessions.create_index("last_activity")

            db.metrics_batches.create_index([("window_start_ist_str", -1), ("window_end_ist_str", -1)])
            db.metrics_batches.create_index([("user_id", 1), ("window_start_ist_str", -1)])
            
            db.incidents.create_index([("window_start_ist_str", -1), ("severity", 1)])
            db.incidents.create_index([("ip", 1), ("window_start_ist_str", -1)])
            db.incidents.create_index([("user_id", 1), ("severity", 1)])
            
            db.anomalies.create_index([("window_start_ist_str", -1), ("instance", 1)])
            db.anomalies.create_index([("ip", 1), ("window_start_ist_str", -1)])
            db.anomalies.create_index([("user_id", 1), ("created_at_ist", -1)])
            
            db.rca.create_index([("user_id", 1), ("timestamp_ist", -1)])
            
            db.targets.create_index([("user_id", 1), ("endpoint", 1)])
            
            _migrate_alert_windows_for_tenant_scoping(db)
            db.alert_windows.create_index(
                [("user_id", 1), ("window_start_ist_str", 1), ("window_end_ist_str", 1)],
                unique=True,
            )
            db.alert_windows.create_index([("user_id", 1), ("window_start_ist_str", 1)])

            # Langfuse ingestion indexes
            db.langfuse_traces.create_index("trace_id", unique=True)
            db.langfuse_traces.create_index([("langfuse_user_id", 1), ("timestamp", -1)])
            db.langfuse_traces.create_index("timestamp")
            # Compound unique: each app user can watch the same Langfuse user independently
            db.langfuse_watched_users.create_index(
                [("langfuse_user_id", 1), ("added_by", 1)], unique=True
            )
            db.langfuse_rca.create_index("timestamp")

            logger.info("[Database] Indexes created")
        except Exception as e:
            logger.warning(f"[Database] Index warning: {e}")

    # Regenerate targets.json from DB on startup to ensure user_id ↔ IP labels are in sync.
    # This fixes stale label mappings left by manual edits or migration scripts.
    if db is not None:
        try:
            from app.api.endpoints.target import _regenerate_targets_file
            _regenerate_targets_file(db)
            logger.info("[Targets] targets.json regenerated from DB on startup")
        except Exception as e:
            logger.warning(f"[Targets] Could not regenerate targets.json on startup: {e}")

    # Start multi-user monitor manager
    monitor_manager.start()
    await monitor_manager.refresh_monitors()  # Initial refresh

    # Start Langfuse polling task
    langfuse_poll_task = asyncio.create_task(poll_langfuse())
    logger.info("[Langfuse] Polling task started")

    async def cleanup_sessions():
        while True:
            await asyncio.sleep(3600)
            cleanup_db = get_db()
            if cleanup_db is not None:
                session_manager.cleanup_old_sessions(cleanup_db, hours=720)

    cleanup_task = asyncio.create_task(cleanup_sessions())

    logger.info("[Startup] ✅ Ready")
    logger.info("=" * 60)

    yield

    logger.info("[Shutdown] Stopping services...")
    await monitor_manager.stop()
    langfuse_poll_task.cancel()
    cleanup_task.cancel()
    try:
        await langfuse_poll_task
    except asyncio.CancelledError:
        pass
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("[Shutdown] ✅ Complete")


app = FastAPI(
    title="AI DevOps Monitor",
    description="Intelligent monitoring with LLM-based anomaly detection and AI-powered RCA (IST Timezone)",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5173/",
        "http://localhost:5174",
        "http://localhost:5174/",
        "http://localhost:5175",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app)

app.include_router(api_router)

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=False
    )
