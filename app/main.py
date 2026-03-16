import asyncio
import os
import json
import uvicorn
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timedelta

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("[Startup] AI DevOps Monitor v2.0")
    logger.info("[Config] Timezone: IST (UTC+5:30)")
    logger.info(f"[Config] Current Time: {format_ist(now_ist())}")
    logger.info(f"[Config] Prometheus: {PROM_URL or 'NOT SET'}")
    
    # LLM Provider logging
    logger.info(f"[Config] LLM Provider: Google Gemini")
    logger.info(f"[Config] GEMINI_MODEL: {os.getenv('GEMINI_MODEL', 'gemini-2.0-flash')}")
    logger.info(f"[Config] GEMINI_API_KEY: {'✅ Set' if (os.getenv('GEMINI_API_KEY') or '').strip() else '❌ NOT SET'}")
    
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
            
            db.alert_windows.create_index([("user_id", 1), ("window_start_ist_str", 1), ("window_end_ist_str", 1)], unique=True)
            db.alert_windows.create_index([("user_id", 1), ("window_start_ist_str", 1)])

            # Migrate legacy alert_windows documents that pre-date per-tenant scoping.
            # Documents without user_id would violate the unique index if two tenants
            # process the same window string — tag them so they don't collide.
            legacy_count = db.alert_windows.count_documents({"user_id": {"$exists": False}})
            if legacy_count:
                db.alert_windows.update_many(
                    {"user_id": {"$exists": False}},
                    {"$set": {"user_id": "__legacy__"}},
                )
                logger.warning(
                    f"[Database] Migrated {legacy_count} legacy alert_windows "
                    "documents to user_id='__legacy__'"
                )

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
        "http://localhost:3000",
        "http://localhost:3080",
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