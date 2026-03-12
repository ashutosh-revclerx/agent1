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


class BatchMonitor:
    """Handles batch metric analysis with LLM-based anomaly detection"""

    def __init__(self, interval_minutes: int = BATCH_INTERVAL_MINUTES, user_id: str = None):
        self.interval = interval_minutes
        self.max_metrics = int(os.getenv("BATCH_MAX_METRICS", "600"))
        self.user_id = user_id  # User ID for multi-user support
        self._task: Optional[asyncio.Task] = None

    def get_window(self) -> Tuple[datetime, datetime]:
        """Calculate current batch window in IST."""
        from datetime import timezone
        current_ist = now_ist()
        current_utc = ist_to_utc(current_ist)
        start_utc, end_utc = make_batch_window(current_utc.replace(tzinfo=None), self.interval)

        # Convert back to IST-aware datetimes properly
        start_ist = start_utc.replace(tzinfo=timezone.utc).astimezone(current_ist.tzinfo)
        end_ist = end_utc.replace(tzinfo=timezone.utc).astimezone(current_ist.tzinfo)
        return start_ist, end_ist

    def get_session_id(self, window_start: datetime) -> str:
        """Generate Langfuse session ID for batch (expects naive UTC)."""
        utc_start = ist_to_utc(window_start).replace(tzinfo=None)
        session_id = make_batch_session_id(utc_start, self.interval, "batch")
        # Add user_id to session for multi-user tracking
        if self.user_id:
            session_id = f"{session_id}_user_{self.user_id}"
        return session_id

    def is_processed(self, db, start: datetime, end: datetime) -> bool:
        """Check if window already processed for this user."""
        if db is None:
            return False
        query = {
            "window_start_ist_str": format_ist(start, include_tz=True),
            "window_end_ist_str": format_ist(end, include_tz=True)
        }
        # Add user_id filter for multi-user
        if self.user_id:
            query["user_id"] = self.user_id
        return db.alert_windows.find_one(query) is not None

    def mark_processed(self, db, start: datetime, end: datetime, session_id: str, incident_id: Any):
        """Mark window as processed for this user."""
        if db is None:
            return

        doc = {
            "window_start_ist": start,
            "window_end_ist": end,
            "window_start_ist_str": format_ist(start, include_tz=True),
            "window_end_ist_str": format_ist(end, include_tz=True),

            "processed_at_ist": now_ist(),
            "processed_at_ist_str": format_ist(now_ist(), include_tz=True),
            "timezone": "IST",

            "langfuse_session_id": session_id,
            "incident_id": incident_id,
        }
        
        # Add user_id for multi-user
        if self.user_id:
            doc["user_id"] = self.user_id

        db.alert_windows.update_one(
            {
                "window_start_ist_str": format_ist(start, include_tz=True),
                "window_end_ist_str": format_ist(end, include_tz=True),
                **({"user_id": self.user_id} if self.user_id else {})
            },
            {"$set": doc},
            upsert=True
        )

    def build_prompt(self, metrics: List[Dict], start: datetime, end: datetime) -> str:
        """Build LLM analysis prompt with IST times."""
        grouped: Dict[str, List[Dict]] = {}
        for m in metrics:
            inst = m.get("instance", "unknown")
            grouped.setdefault(inst, []).append(m)

        lines, total = [], 0
        for inst, inst_metrics in sorted(grouped.items()):
            lines.append(f"\n### Instance: {inst}")
            for m in sorted(inst_metrics, key=lambda x: x.get("name", ""))[:200]:
                if total >= self.max_metrics:
                    break
                lines.append(f"  {m['name']}: {m['value']}")
                total += 1
            if total >= self.max_metrics:
                lines.append(f"\n  ... (capped at {self.max_metrics})")
                break

        schema = {
            "incident": {
                "title": "string", "severity": "low|medium|high|critical",
                "confidence": 0.0, "summary": "string", "root_cause": "string",
                "contributing_factors": [], "blast_radius": "string",
                "evidence": [{"metric": "", "instance": "", "value": 0, "why_it_matters": ""}],
                "fix_plan": {"immediate": [], "next_24h": [], "prevention": []}
            },
            "anomalies": [{"metric": "", "instance": "", "observed": 0, "expected": "", "symptom": "", "cluster": ""}],
            "clusters": [{"name": "", "theme": "", "anomaly_indexes": []}]
        }

        start_str = format_ist(start, include_tz=True)
        end_str = format_ist(end, include_tz=True)

        return f"""You are an expert SRE analyzing Prometheus metrics.

BATCH WINDOW (IST): {start_str} -> {end_str} ({self.interval} min)

TASKS:
1. Detect anomalies (spikes, drops, errors, high resource usage)
2. Cluster related anomalies by root cause
3. Provide collective RCA with evidence
4. Return ONLY valid JSON (no markdown)

METRICS ({total}/{len(metrics)} included):
{"".join(lines)}

SCHEMA:
{json.dumps(schema, indent=2)}

RETURN ONLY JSON:"""

    async def call_llm(self, prompt: str, session_id: str, metadata: Dict) -> Dict:
        # ✅ LLM model/provider is read by ask_llm() from env
        result = await asyncio.get_running_loop().run_in_executor(
            None, ask_llm, prompt, "Batch Collective RCA", metadata, session_id
        )
        if not result:
            return {}
        text, _ = result
        return parse_json(text) if text else {}

    def _pick_primary_instance(self, metrics: List[Dict], analysis: Dict) -> str:
        """Pick a real ip:port instance. Never use blast_radius."""
        inc = analysis.get("incident", {}) or {}
        candidates: List[str] = []

        for a in (analysis.get("anomalies", []) or []):
            inst = a.get("instance")
            if looks_like_instance(inst):
                candidates.append(inst)

        for e in (inc.get("evidence", []) or []):
            inst = e.get("instance")
            if looks_like_instance(inst):
                candidates.append(inst)

        for m in (metrics or []):
            inst = m.get("instance")
            if looks_like_instance(inst):
                candidates.append(inst)

        return candidates[0] if candidates else "unknown"

    def store_results(self, db, start: datetime, end: datetime, session_id: str,
                      metrics: List[Dict], analysis: Dict) -> Tuple[Any, Any]:
        """Store results; DB will ALWAYS have correct instance/ip/port and user_id."""
        if db is None:
            return None, None

        created_ist = now_ist()

        created_ist_str = format_ist(created_ist, include_tz=True)
        start_ist_str = format_ist(start, include_tz=True)
        end_ist_str = format_ist(end, include_tz=True)

        primary_instance = self._pick_primary_instance(metrics, analysis)
        ip, port = parse_instance(primary_instance)
        source_obj = build_source(instance=primary_instance)

        batch_id = incident_id = None
        try:
            batch_doc = {
                "window_start_ist": start,
                "window_end_ist": end,
                "collected_at_ist": created_ist,
                "timezone": "IST",

                "window_start_ist_str": start_ist_str,
                "window_end_ist_str": end_ist_str,
                "collected_at_ist_str": created_ist_str,

                "metrics_count": len(metrics),
                "metrics": metrics,

                "instance": primary_instance,
                "ip": ip,
                "port": port,
                "source": source_obj,

                "langfuse_session_id": session_id,
            }
            # Add user_id for multi-user
            if self.user_id:
                batch_doc["user_id"] = self.user_id
            
            batch_id = db.metrics_batches.insert_one(batch_doc).inserted_id

            inc = analysis.get("incident", {}) or {}

            incident_doc = {
                "created_at_ist": created_ist,
                "timezone": "IST",
                "created_at_ist_str": created_ist_str,

                "window_start_ist": start,
                "window_end_ist": end,
                "window_start_ist_str": start_ist_str,
                "window_end_ist_str": end_ist_str,

                "batch_id": batch_id,

                "instance": primary_instance,
                "ip": ip,
                "port": port,
                "source": source_obj,

                "title": inc.get("title", "Batch Analysis"),
                "severity": inc.get("severity", "low"),
                "confidence": float(inc.get("confidence", 0)),
                "summary": inc.get("summary", ""),
                "root_cause": inc.get("root_cause", ""),
                "contributing_factors": inc.get("contributing_factors", []),

                "blast_radius": inc.get("blast_radius", ""),

                "evidence": inc.get("evidence", []),
                "fix_plan": inc.get("fix_plan", {}),
                "clusters": analysis.get("clusters", []),
                "langfuse_session_id": session_id,
                "raw_analysis": analysis,
            }
            # Add user_id for multi-user
            if self.user_id:
                incident_doc["user_id"] = self.user_id
            
            incident_id = db.incidents.insert_one(incident_doc).inserted_id

            anomalies = analysis.get("anomalies", []) or []
            if anomalies:
                docs = []
                for a in anomalies:
                    inst = a.get("instance", "unknown")
                    if not looks_like_instance(inst):
                        inst = primary_instance

                    a_ip, a_port = parse_instance(inst)
                    anomaly_doc = {
                        "created_at_ist": created_ist,
                        "timezone": "IST",
                        "created_at_ist_str": created_ist_str,

                        "window_start_ist": start,
                        "window_end_ist": end,
                        "window_start_ist_str": start_ist_str,
                        "window_end_ist_str": end_ist_str,

                        "batch_id": batch_id,
                        "incident_id": incident_id,

                        "metric": a.get("metric"),
                        "instance": inst,
                        "ip": a_ip,
                        "port": a_port,
                        "source": build_source(instance=inst),

                        "observed": a.get("observed"),
                        "expected": a.get("expected"),
                        "symptom": a.get("symptom"),
                        "cluster": a.get("cluster"),
                        "langfuse_session_id": session_id,
                    }
                    # Add user_id for multi-user
                    if self.user_id:
                        anomaly_doc["user_id"] = self.user_id
                    docs.append(anomaly_doc)
                db.anomalies.insert_many(docs)

            rca_doc = {
                "timestamp_ist": created_ist,
                "timezone": "IST",
                "timestamp_ist_str": created_ist_str,

                "window_start_ist": start,
                "window_end_ist": end,
                "window_start_ist_str": start_ist_str,
                "window_end_ist_str": end_ist_str,

                "batch_id": batch_id,
                "incident_id": incident_id,

                "instance": primary_instance,
                "ip": ip,
                "port": port,
                "source": source_obj,

                "summary": inc.get("summary"),
                "cause": inc.get("root_cause"),
                "fix": inc.get("fix_plan", {}).get("immediate", []),
                "langfuse_session_id": session_id,
                "raw": analysis,
            }
            # Add user_id for multi-user
            if self.user_id:
                rca_doc["user_id"] = self.user_id
            
            db.rca.insert_one(rca_doc)

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
            success, reason = send_alert(f"[{sev}] {title}", html, user_id=self.user_id)
            if not success:
                logger.warning(f"[Alerts] Email not sent: {reason}")
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

            llm_metadata = {
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
                "metrics_count": len(metrics),
                "timezone": "IST",
                "user_id": self.user_id,
                "llm_provider": "google_gemini",
                "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
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

            _, incident_id = self.store_results(db, start, end, session_id, metrics, analysis)
            self.send_alerts(incident, anomalies, start, end, session_id)
            self.mark_processed(db, start, end, session_id, incident_id)

        finally:
            if prop_ctx:
                try:
                    prop_ctx.__exit__(None, None, None)
                except Exception:
                    pass
            if span_ctx:
                try:
                    span_ctx.__exit__(None, None, None)
                except Exception:
                    pass

        logger.info(f"[Batch]{user_log} Complete: {window_str}")

    async def run_loop(self):
        """Continuous batch monitoring loop with IST scheduling."""
        logger.info(f"[Batch] Monitor started (every {self.interval} min)")

        while True:
            try:
                now = now_ist()
                # Guard against intervals >= 60 minutes
                if self.interval >= 60:
                    # For hour+ intervals, align to the start of the hour
                    total_minutes = now.hour * 60 + now.minute
                    bucket_minutes = (total_minutes // self.interval) * self.interval
                    next_bucket = bucket_minutes + self.interval
                    next_run = now.replace(hour=next_bucket // 60, minute=next_bucket % 60, second=0, microsecond=0)
                    if next_run <= now:
                        next_run += timedelta(minutes=self.interval)
                else:
                    bucket = (now.minute // self.interval) * self.interval
                    next_run = now.replace(minute=bucket, second=0, microsecond=0)
                    if now >= next_run:
                        next_run += timedelta(minutes=self.interval)

                sleep_sec = (next_run - now).total_seconds()
                if sleep_sec > 0:
                    logger.info(f"[Batch] Next run: {next_run.strftime('%H:%M:%S')} IST ({sleep_sec:.0f}s)")
                    await asyncio.sleep(sleep_sec)

                await self.run_worker()

            except asyncio.CancelledError:
                logger.info("[Batch] Monitor stopped")
                break
            except Exception as e:
                logger.error(f"[Batch] Error: {e}", exc_info=True)
                await asyncio.sleep(60)

    def start(self) -> asyncio.Task:
        self._task = asyncio.create_task(self.run_loop())
        return self._task

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


class UserBatchMonitorManager:
    """Manages batch monitors for multiple users"""
    
    def __init__(self):
        self.monitors: Dict[str, BatchMonitor] = {}
        self._refresh_task: Optional[asyncio.Task] = None
    
    async def refresh_monitors(self):
        """Refresh monitors based on users with active targets"""
        db = get_db()
        if db is None:
            return
        
        try:
            # Get all unique user_ids with enabled targets
            user_ids = db.targets.distinct("user_id", {"enabled": True})
            
            # Start monitors for new users
            for user_id in user_ids:
                if user_id and user_id not in self.monitors:
                    logger.info(f"[MonitorManager] Starting monitor for user: {user_id}")
                    monitor = BatchMonitor(user_id=user_id)
                    monitor.start()
                    self.monitors[user_id] = monitor
            
            # Stop monitors for users without targets
            to_remove = []
            for user_id in self.monitors:
                if user_id not in user_ids:
                    logger.info(f"[MonitorManager] Stopping monitor for user: {user_id}")
                    await self.monitors[user_id].stop()
                    to_remove.append(user_id)
            
            for user_id in to_remove:
                del self.monitors[user_id]
                
        except Exception as e:
            logger.error(f"[MonitorManager] Error refreshing monitors: {e}")
    
    async def refresh_loop(self):
        """Periodically refresh monitors (every 5 minutes)"""
        while True:
            try:
                await self.refresh_monitors()
                await asyncio.sleep(300)  # 5 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[MonitorManager] Refresh loop error: {e}")
                await asyncio.sleep(60)
    
    def start(self):
        """Start the monitor manager"""
        self._refresh_task = asyncio.create_task(self.refresh_loop())
        logger.info("[MonitorManager] Started")
    
    async def stop(self):
        """Stop all monitors"""
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        
        for user_id, monitor in self.monitors.items():
            logger.info(f"[MonitorManager] Stopping monitor for user: {user_id}")
            await monitor.stop()
        
        self.monitors.clear()
        logger.info("[MonitorManager] Stopped")


monitor_manager = UserBatchMonitorManager()


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

            # Langfuse ingestion indexes
            db.langfuse_traces.create_index("trace_id", unique=True)
            db.langfuse_traces.create_index([("langfuse_user_id", 1), ("timestamp", -1)])
            db.langfuse_traces.create_index("timestamp")
            db.langfuse_watched_users.create_index("langfuse_user_id", unique=True)
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
    allow_origins=["http://localhost:5173", "http://localhost:5173/", "http://localhost:3000"],
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