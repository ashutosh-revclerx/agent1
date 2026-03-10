"""
Application Settings
Loads and validates environment variables
"""
import os
from dotenv import load_dotenv

load_dotenv(override=True)

# Prometheus
PROM_URL = os.getenv("PROM_URL", "http://localhost:9090")

# MongoDB
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB", "observability")
MAX_DOCS = int(os.getenv("MAX_DOCS", "1000"))

# Gemini (Primary LLM)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()

# LLM (gemma3:1b - Fallback)
LLM_URL = os.getenv("LLM_URL")
LLM_MODEL = os.getenv("LLM_MODEL", "gemma3:1b")

# Monitoring / Batch job
# NOTE: interval is in seconds. Default = 30 minutes.
MONITOR_INTERVAL = int(os.getenv("MONITOR_INTERVAL", "1800"))

# If your Prometheus returns thousands of series, we cap what we send to the LLM.
BATCH_MAX_METRICS = int(os.getenv("BATCH_MAX_METRICS", "600"))
BATCH_INTERVAL_MINUTES = int(os.getenv("BATCH_INTERVAL_MINUTES", "2"))
# Maximum metrics per instance (for better prompt organization)
BATCH_METRICS_PER_INSTANCE = int(os.getenv("BATCH_METRICS_PER_INSTANCE", "200"))

# Maximum instances to include in prompt (top N by metric count)
BATCH_TOP_INSTANCES = int(os.getenv("BATCH_TOP_INSTANCES", "6"))

# Email
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
_emails = os.getenv("ALERT_EMAILS", "") or os.getenv("ALERT_EMAIL", "")
ALERT_EMAILS = [e.strip() for e in _emails.split(",") if e.strip()]

# Slack (Incoming Webhook)
SLACK_ENABLED = os.getenv("SLACK_ENABLED", "false").strip().lower() in ("1", "true", "yes", "y", "on")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "").strip()

# Langfuse
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com").strip()
