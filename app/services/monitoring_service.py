import asyncio
import os
import json
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timedelta, timezone

from app.core.config import BATCH_INTERVAL_MINUTES, PROM_URL
from app.core.logging import logger
from app.core.time import now_ist, ist_to_utc, format_ist
from app.core.helpers import parse_json
from app.services.langfuse_service import (
    is_langfuse_enabled, get_langfuse_client, 
    make_batch_session_id, make_batch_window
)
from app.services.slack_service import send_slack_alert_text, slack_is_configured
from app.services.email_service import send_alert
from app.services.mongodb_service import get_db, parse_instance, build_source, looks_like_instance
from app.services.prometheus_service import fetch_metrics, fetch_metrics_for_user
from app.services.llm_service import ask_llm

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
        if self.user_id:
            session_id = f"{session_id}_user_{self.user_id}"
        return session_id

    def claim_window(self, db, start: datetime, end: datetime) -> bool:
        if db is None: return False
        if not self.user_id:
            logger.error("[Batch] user_id is required for window claiming — skipping")
            return False

        placeholder = {
            "user_id": self.user_id,
            "window_start_ist": start,
            "window_end_ist": end,
            "window_start_ist_str": format_ist(start, include_tz=True),
            "window_end_ist_str": format_ist(end, include_tz=True),
            "status": "processing",
            "claimed_at_ist": now_ist(),
            "timezone": "IST",
        }
        try:
            db.alert_windows.insert_one(placeholder)
            return True
        except Exception as e:
            if "duplicate" in str(e).lower() or "E11000" in str(e):
                return False
            logger.error(f"[Batch] Unexpected error claiming window: {e}", exc_info=True)
            return False

    def mark_processed(self, db, start: datetime, end: datetime, session_id: str, incident_id: Any):
        if db is None or not self.user_id: return
        db.alert_windows.update_one(
            {
                "user_id": self.user_id,
                "window_start_ist_str": format_ist(start, include_tz=True),
                "window_end_ist_str": format_ist(end, include_tz=True),
            },
            {
                "$set": {
                    "status": "processed",
                    "processed_at_ist": now_ist(),
                    "processed_at_ist_str": format_ist(now_ist(), include_tz=True),
                    "langfuse_session_id": session_id,
                    "incident_id": incident_id,
                }
            },
            upsert=False,
        )

    def build_prompt(self, metrics: List[Dict], start: datetime, end: datetime) -> str:
        grouped: Dict[str, List[Dict]] = {}
        for m in metrics:
            inst = m.get("instance", "unknown")
            grouped.setdefault(inst, []).append(m)

        lines, total = [], 0
        for inst, inst_metrics in sorted(grouped.items()):
            lines.append(f"\n### Instance: {inst}")
            for m in sorted(inst_metrics, key=lambda x: x.get("name", ""))[:200]:
                if total >= self.max_metrics: break
                lines.append(f"  {m['name']}: {m['value']}")
                total += 1
            if total >= self.max_metrics: break

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

        return f"""You are an expert SRE analyzing Prometheus metrics.
BATCH WINDOW (IST): {format_ist(start, include_tz=True)} -> {format_ist(end, include_tz=True)}
METRICS ({total}/{len(metrics)} included):
{"".join(lines)}
SCHEMA: {json.dumps(schema, indent=2)}
RETURN ONLY JSON:"""

    async def call_llm(self, prompt: str, session_id: str, metadata: Dict) -> Dict:
        result = await asyncio.get_running_loop().run_in_executor(
            None, ask_llm, prompt, "Batch Collective RCA", metadata, session_id
        )
        if not result: return {}
        text, _ = result
        return parse_json(text) if text else {}

    def _pick_primary_instance(self, metrics: List[Dict], analysis: Dict) -> str:
        candidates: List[str] = []
        for a in (analysis.get("anomalies", []) or []):
            inst = a.get("instance")
            if looks_like_instance(inst): candidates.append(inst)
        for m in (metrics or []):
            inst = m.get("instance")
            if looks_like_instance(inst): candidates.append(inst)
        return candidates[0] if candidates else "unknown"

    def store_results(self, db, start: datetime, end: datetime, session_id: str,
                      metrics: List[Dict], analysis: Dict) -> Tuple[Any, Any]:
        if db is None: return None, None
        created_ist = now_ist()
        primary_instance = self._pick_primary_instance(metrics, analysis)
        ip, port = parse_instance(primary_instance)
        source_obj = build_source(instance=primary_instance)

        inc = analysis.get("incident", {}) or {}
        anomalies = analysis.get("anomalies", []) or []

        try:
            batch_doc = {
                "window_start_ist": start, "window_end_ist": end,
                "collected_at_ist": created_ist, "user_id": self.user_id,
                "metrics": metrics, "analysis": analysis
            }
            res_batch = db.metrics_batches.insert_one(batch_doc)
            batch_id = res_batch.inserted_id

            inc_doc = {
                "batch_id": batch_id, "user_id": self.user_id,
                "created_at_ist": created_ist, "ip": ip, "port": port,
                **inc
            }
            res_inc = db.incidents.insert_one(inc_doc)
            incident_id = res_inc.inserted_id

            for idx, a in enumerate(anomalies):
                a_doc = {
                    "batch_id": batch_id, "incident_id": incident_id,
                    "user_id": self.user_id, "created_at_ist": created_ist,
                    "ip": ip, "port": port, **a
                }
                db.anomalies.insert_one(a_doc)

            rca_doc = {
                "user_id": self.user_id, "created_at_ist": created_ist,
                "window_start_ist": start, "window_end_ist": end,
                "batch_id": batch_id, "incident_id": incident_id,
                "instance": primary_instance, "ip": ip, "port": port,
                "summary": inc.get("summary"), "cause": inc.get("root_cause"),
                "fix": inc.get("fix_plan", {}).get("immediate", []),
                "langfuse_session_id": session_id, "raw": analysis
            }
            db.rca.insert_one(rca_doc)
            return batch_id, incident_id
        except Exception as e:
            logger.error(f"[Batch] Storage error: {e}", exc_info=True)
            return None, None

    def send_alerts(self, incident: Dict, anomalies: List, start: datetime, end: datetime, session_id: str):
        sev = incident.get("severity", "low").upper()
        title = incident.get("title", "Batch Analysis")
        summary = incident.get("summary", "No summary provided")
        root_cause = incident.get("root_cause", "Unknown")
        confidence = incident.get("confidence", "N/A")
        
        window = f"{start.strftime('%Y-%m-%d %H:%M')} -> {end.strftime('%H:%M')} IST"
        
        # --- SLACK ALERT ---
        if slack_is_configured(user_id=self.user_id):
            slack_msg = (
                f"🚨 *[{sev}] {title}*\n"
                f"📅 *Window:* {window}\n"
                f"📝 *Summary:* {summary}\n"
                f"🔍 *Root Cause:* {root_cause}\n"
                f"📊 *Anomalies:* {len(anomalies)}\n"
                f"🎯 *Confidence:* {confidence}\n"
                f"🔗 *Session:* `{session_id}`"
            )
            send_slack_alert_text(slack_msg, user_id=self.user_id)
        
        # --- EMAIL ALERT ---
        # Build anomaly rows
        anomaly_rows = "".join(
            f"<tr>"
            f"<td><b>{a.get('metric', 'N/A')}</b></td>"
            f"<td><code>{a.get('instance', 'unknown')}</code></td>"
            f"<td>{a.get('observed', 'N/A')}</td>"
            f"<td>{a.get('expected', 'N/A')}</td>"
            f"<td>{a.get('symptom', '—')}</td>"
            f"</tr>"
            for a in anomalies[:15]
        )

        # Build Fix Plan
        fix_plan = incident.get("fix_plan", {})
        immediate_actions = fix_plan.get("immediate", []) if isinstance(fix_plan, dict) else []
        fix_html = "".join(f"<li>{action}</li>" for action in immediate_actions) or "<li>No immediate actions specified</li>"

        subject = f"[{sev}] Monitoring Alert: {title}"
        
        html = f"""
        <div style="font-family: sans-serif; max-width: 800px; color: #333;">
            <h2 style="color: {'#d32f2f' if sev in ('CRITICAL', 'HIGH') else '#f57c00'};">
                🚨 [{sev}] {title}
            </h2>
            <p><b>Time Window (IST):</b> {window}</p>
            
            <div style="background: #f5f5f5; padding: 15px; border-left: 4px solid #334155; margin-bottom: 20px;">
                <p style="margin-top: 0;"><b>Summary:</b> {summary}</p>
                <p><b>Root Cause:</b> {root_cause}</p>
                <p style="margin-bottom: 0;"><b>Confidence Score:</b> {confidence}</p>
            </div>

            <h3>📊 Detected Anomalies ({len(anomalies)})</h3>
            <table border="1" cellpadding="8" style="border-collapse: collapse; width: 100%; font-size: 14px; margin-bottom: 20px;">
                <tr style="background: #f8fafc;">
                    <th align="left">Metric</th>
                    <th align="left">Instance</th>
                    <th align="left">Observed</th>
                    <th align="left">Expected</th>
                    <th align="left">Symptom</th>
                </tr>
                {anomaly_rows}
            </table>

            <h3>⚡ Recommended Immediate Actions</h3>
            <ul style="padding-left: 20px;">
                {fix_html}
            </ul>

            <hr style="border: 0; border-top: 1px solid #eee; margin: 30px 0;">
            <p style="font-size: 12px; color: #666;">
                <b>Session ID:</b> {session_id}<br>
                This alert was generated by AI DevOps Monitoring Service for user {self.user_id}.
            </p>
        </div>
        """
        
        send_alert(subject, html, user_id=self.user_id)

    async def run_worker(self):
        start, end = self.get_window()
        session_id = self.get_session_id(start)
        db = get_db()
        if not self.claim_window(db, start, end): return

        langfuse = get_langfuse_client()
        span_ctx = None
        if langfuse and is_langfuse_enabled() and hasattr(langfuse, 'start_as_current_observation'):
            try:
                span_ctx = langfuse.start_as_current_observation(
                    as_type="span", name="Batch Monitoring",
                    metadata={"user_id": self.user_id}
                )
                span_ctx.__enter__()
            except Exception as e:
                logger.warning(f"[Langfuse] Span error (skipping tracing): {e}")
                span_ctx = None

        try:
            metrics = await fetch_metrics_for_user(self.user_id) if self.user_id else await fetch_metrics()
            if not metrics:
                logger.info(f"[Batch] No metrics for user {self.user_id} yet - skipping window")
                return
            analysis = await self.call_llm(self.build_prompt(metrics, start, end), session_id, {"user_id": self.user_id})
            if not analysis: return
            
            _, incident_id = self.store_results(db, start, end, session_id, metrics, analysis)
            self.send_alerts(analysis.get("incident", {}), analysis.get("anomalies", []), start, end, session_id)
            self.mark_processed(db, start, end, session_id, incident_id)
            logger.info(f"[Batch] ✅ Window complete for user {self.user_id}")
        finally:
            if span_ctx:
                try: span_ctx.__exit__(None, None, None)
                except Exception: pass


    async def run_loop(self):
        logger.info(f"[Batch] Monitor started for user {self.user_id}")
        while True:
            try:
                now = now_ist()
                bucket = (now.minute // self.interval) * self.interval
                next_run = now.replace(minute=bucket, second=0, microsecond=0) + timedelta(minutes=self.interval)
                sleep_sec = (next_run - now).total_seconds()
                if sleep_sec > 0: await asyncio.sleep(sleep_sec)
                await self.run_worker()
            except asyncio.CancelledError: break
            except Exception as e:
                logger.error(f"[Batch] Error for user {self.user_id}: {e}")
                await asyncio.sleep(60)

    def start(self):
        self._task = asyncio.create_task(self.run_loop())

    async def stop(self):
        if self._task:
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass

class UserBatchMonitorManager:
    def __init__(self):
        self.monitors: Dict[str, BatchMonitor] = {}
        self._refresh_task: Optional[asyncio.Task] = None

    async def refresh_monitors(self):
        db = get_db()
        if db is None: return
        user_ids = db.targets.distinct("user_id", {"enabled": True})
        for uid in user_ids:
            if uid and uid not in self.monitors:
                logger.info(f"[MonitorManager] Starting monitor for user: {uid}")
                m = BatchMonitor(user_id=uid)
                m.start()
                self.monitors[uid] = m
        
        to_remove = [uid for uid in self.monitors if uid not in user_ids]
        for uid in to_remove:
            logger.info(f"[MonitorManager] Stopping monitor for user: {uid}")
            await self.monitors[uid].stop()
            del self.monitors[uid]

    async def refresh_loop(self):
        while True:
            await self.refresh_monitors()
            await asyncio.sleep(300)

    def start(self):
        self._refresh_task = asyncio.create_task(self.refresh_loop())

    async def stop(self):
        if self._refresh_task: self._refresh_task.cancel()
        for m in self.monitors.values(): await m.stop()
        self.monitors.clear()

monitor_manager = UserBatchMonitorManager()
