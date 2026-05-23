# AI DevOps Monitoring & Analysis Platform

**Multi-user intelligent infrastructure monitoring with AI-powered root cause analysis**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![MongoDB](https://img.shields.io/badge/MongoDB-6.0+-success.svg)](https://www.mongodb.com/)
[![React](https://img.shields.io/badge/React-19+-61DAFB.svg)](https://reactjs.org/)
[![Firebase](https://img.shields.io/badge/Firebase-Auth-orange.svg)](https://firebase.google.com/)

> Production-ready SaaS platform for real-time infrastructure monitoring with LLM-powered anomaly detection, batch analysis, Langfuse observability, and intelligent alerting.

---

## Recent Updates

### v2.6.0 - March 2026
- **Connectivity Resilience**: Implemented persistent connection pooling and `urllib3`-level exponential backoff in the Langfuse ingestion service to eliminate `ConnectionResetError` (10054).
- **Intelligent Backfill**: Ingestion service now tracks `last_polled_at` and automatically performs up to a 24-hour backfill on startup or for new users.
- **Frontend Auto-Pagination**: The API service now automatically fetches all data pages for Anomalies, RCA, Batches, and Incidents, providing a seamless scrolling experience.
- **Manual RCA Trigger**: Added capability to trigger Root Cause Analysis on-demand from the Langfuse Monitor UI.
- **Hardened Security**: Environment loading now uses `.strip()` to prevent hidden trailing spaces from corrupting credentials; improved SSRF validation.

### v2.5.0 - March 2026

---

## Overview

AI DevOps Monitor is a complete multi-user monitoring platform that collects Prometheus metrics and uses Large Language Models (Gemini primary, Gemma3 fallback) to detect anomalies, identify root causes, and provide actionable remediation steps. Each user has their own isolated workspace with custom monitoring targets and notification settings.

### Key Features

- **LibreChat Analysis Hub** - Embedded advanced chat interface with AI SRE persona for deep infrastructure analysis
- **100% LLM-Powered Detection** - AI detects anomalies from raw metrics — no threshold rules, no manual configuration
- **Langfuse Observability** - Traces every LLM call; ingests external traces from watched users; full RCA dashboard
- **Firebase Authentication** - Email/password and Google OAuth; multi-device session tracking; JWT-based API auth
- **Batch Analysis** - Holistic incident detection by analyzing complete metric batches per user
- **Multi-User Architecture** - Complete user isolation with user_id filtering on every database query
- **Intelligent Alerting** - Email and Slack alerts with automated Root Cause Analysis and remediation steps
- **Dynamic Target Management** - Add/remove Prometheus targets from the UI; targets.json auto-regenerated with auto-synchronization
- **Grafana Integration** - Universal dashboards auto-detecting Windows Exporter and Node Exporter metrics
- **IST Timezone** - Consistent Indian Standard Time across all timestamps and batch windows
- **Resilient Ingestion** - Robust metric ingestion pipeline with retry mechanisms and error handling.
- **Intelligent Backfill** - Automatically backfills missing metric data to ensure continuous analysis.
- **Auto-Pagination** - Frontend API client automatically handles pagination for large datasets.

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- MongoDB 6.0+
- Docker (for Prometheus and Grafana)
- Google Gemini API key
- Firebase project with Authentication enabled

### 1. Backend Setup

```bash
# Clone repository
git clone https://github.com/yourusername/ai-devops-monitor.git
cd ai-devops-monitor

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings (see Configuration section)
```

### 2. Frontend Setup

```bash
cd frontend
npm install
```

### 3. Start Prometheus & Grafana

```bash
# Using Docker Compose (recommended)
docker-compose up -d

# This starts:
# - Prometheus (port 9099 -> container 9090)
# - Grafana    (port 3001 -> container 3000)
```

### 4. LibreChat Analysis Hub (Optional)

```bash
# Navigate to LibreChat directory
cd LibreChat

# Start the Analysis Hub
docker-compose up -d

# Access LibreChat
# http://localhost:3080
```

### 5. Run the Application

```bash
# Terminal 1: Backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Frontend
cd frontend
npm run dev
```

### 6. Access the Application

| Service | URL | Notes |
|---------|-----|-------|
| Frontend | http://localhost:5173 | Main React UI |
| Backend API Docs | http://localhost:8000/docs | Swagger UI |
| Prometheus | http://localhost:9099 | Metrics scraper |
| Grafana | http://localhost:3001 | Dashboards (admin/admin) |
| LibreChat | http://localhost:3080 | AI SRE command center |

---

## Configuration

### Environment Variables (.env)

```env
# ============================================
# CORE SERVICES
# ============================================
PROM_URL=http://localhost:9099
MONGO_URI=mongodb://localhost:27017
MONGO_DB=observability
BATCH_INTERVAL_MINUTES=2
BATCH_MAX_METRICS=600
MONITOR_INTERVAL=30

# ============================================
# LLM CONFIGURATION (Primary + Fallback)
# ============================================

# Primary LLM: Google Gemini
GEMINI_API_KEY=your-gemini-api-key-here
GEMINI_MODEL=gemini-2.5-pro

# Fallback LLM: Gemma3 via Ollama (auto-fallback if Gemini fails)
LLM_URL=http://localhost:11434
LLM_MODEL=gemma3:1b

# ============================================
# FIREBASE AUTHENTICATION
# ============================================
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_SERVICE_ACCOUNT_PATH=./your-service-account.json
FIREBASE_API_KEY=your-firebase-api-key
FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com

# ============================================
# JWT AUTHENTICATION
# ============================================
JWT_SECRET_KEY=your-super-secret-jwt-key-change-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# ============================================
# LANGFUSE OBSERVABILITY
# ============================================
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com

# ============================================
# EMAIL ALERTS
# ============================================
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
ALERT_EMAIL=alerts@yourdomain.com

# ============================================
# SLACK ALERTS
# ============================================
SLACK_ENABLED=true
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# ============================================
# RATE LIMITING
# ============================================
ENABLE_RATE_LIMITING=true
AUTH_RATE_LIMIT=5/minute
API_RATE_LIMIT=100/minute

# ============================================
# SECURITY
# ============================================
ALLOW_PRIVATE_TARGETS=false   # Set true in dev to allow private IPs

# ============================================
# LIBRECHAT
# ============================================
LIBRECHAT_API_KEY=your-librechat-api-key
```

### Gmail App Password Setup

1. Enable 2-Step Verification: https://myaccount.google.com/security
2. Generate App Password: https://myaccount.google.com/apppasswords
3. Use the 16-character password in `SMTP_PASSWORD`

### Firebase Setup

1. Create a Firebase project at https://console.firebase.google.com
2. Enable **Authentication** → Email/Password and Google providers
3. Go to Project Settings → Service Accounts → Generate new private key
4. Save the JSON file and set `FIREBASE_SERVICE_ACCOUNT_PATH` to its path
5. Copy Web App config values to the corresponding `FIREBASE_*` env vars

### Prometheus Configuration

The system uses **file-based service discovery** for dynamic targets:

**prometheus.yml:**
```yaml
global:
  scrape_interval: 5s

scrape_configs:
  - job_name: "dynamic-targets"
    file_sd_configs:
      - files:
          - "/etc/prometheus/targets.json"
        refresh_interval: 30s
```

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9099:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - ./targets.json:/etc/prometheus/targets.json
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.enable-lifecycle'
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3001:3000"
    environment:
      - GF_AUTH_ANONYMOUS_ENABLED=true
      - GF_AUTH_ANONYMOUS_ORG_ROLE=Admin
    depends_on:
      - prometheus
    restart: unless-stopped

volumes:
  prometheus_data:
```

---

## Project Structure

```
Full-Stack-Engineer-Training-and-Project/
│
├── app/                              # FastAPI backend
│   ├── main.py                       # App entry point, CORS, lifespan
│   │
│   ├── api/                          # API layer
│   │   ├── router.py                 # Central router (includes all endpoints)
│   │   └── endpoints/
│   │       ├── auth.py               # Register, login, sessions (Firebase + JWT)
│   │       ├── chat.py               # External chatbot queries (LibreChat bridge)
│   │       ├── config.py             # Email / Slack config CRUD
│   │       ├── data.py               # Stats, batches, anomalies, RCA, incidents
│   │       ├── health.py             # System health check
│   │       ├── langfuse_monitor.py   # Watched users, traces, RCA from Langfuse
│   │       ├── slack_config.py       # Slack webhook management
│   │       └── target.py             # Prometheus target management
│   │
│   ├── core/                         # Shared utilities
│   │   ├── auth.py                   # JWT creation/validation, Argon2 hashing, Firebase verify
│   │   ├── config.py                 # Environment variable loading (Pydantic Settings)
│   │   ├── firebase.py               # Firebase Admin SDK initialization
│   │   ├── helpers.py                # JSON parsing utilities
│   │   ├── logging.py                # Structured logging setup
│   │   ├── rate_limit.py             # SlowAPI rate limiter
│   │   ├── session.py                # Session create/validate/revoke
│   │   └── time.py                   # IST timezone utilities
│   │
│   ├── schemas/                      # Pydantic request/response models
│   │   ├── auth.py                   # User, Token, Session schemas
│   │   ├── chat.py                   # Chat message and session schemas
│   │   ├── config.py                 # Email config schemas
│   │   ├── slack_config.py           # Slack config schemas
│   │   └── target.py                 # Prometheus target schemas
│   │
│   ├── services/                     # Business logic
│   │   ├── chat_service.py           # Context builder for LibreChat queries
│   │   ├── email_service.py          # SMTP alert email delivery
│   │   ├── langfuse_ingestion_service.py  # Background Langfuse trace polling
│   │   ├── langfuse_service.py       # Langfuse client, session ID generation
│   │   ├── llm_service.py            # Gemini API + fallback Gemma3 integration
│   │   ├── mongodb_service.py        # MongoDB connection, init, SSRF validation
│   │   ├── monitoring_service.py     # Multi-user batch monitoring manager
│   │   ├── prometheus_service.py     # Prometheus range/instant queries
│   │   ├── session_service.py        # Device-aware session management
│   │   └── slack_service.py          # Slack webhook alerts
│   │
│   └── migrations/
│       └── migrate_sessions.py       # Database migration utilities
│
├── frontend/                         # React frontend (Vite + Tailwind CSS)
│   ├── src/
│   │   ├── components/
│   │   │   ├── AIAnalyst.jsx         # Embedded LibreChat iframe
│   │   │   ├── Anomalies.jsx         # AI-detected anomalies table
│   │   │   ├── Dashboard.jsx         # Main overview with stats
│   │   │   ├── EmailSettings.jsx     # Email notification config
│   │   │   ├── LangfuseMonitor.jsx   # Langfuse trace/RCA dashboard
│   │   │   ├── Login.jsx             # Firebase login (email + Google)
│   │   │   ├── MetricsOverview.jsx   # Prometheus batch viewer
│   │   │   ├── Navbar.jsx            # Top navigation bar
│   │   │   ├── ProtectedRoute.jsx    # Auth guard for routes
│   │   │   ├── RCAResults.jsx        # Root cause analysis viewer
│   │   │   ├── Register.jsx          # User registration
│   │   │   ├── ServerSettings.jsx    # Target and Slack management
│   │   │   └── SessionManagement.jsx # Active sessions + revocation
│   │   │
│   │   ├── contexts/
│   │   │   └── AuthContext.jsx       # Firebase auth state + JWT management
│   │   │
│   │   ├── services/
│   │   │   └── api.js                # Centralized API client (auto-pagination, token refresh)
│   │   │
│   │   ├── utils/
│   │   │   └── time.js               # Time formatting utilities
│   │   │
│   │   ├── App.jsx                   # Router, sidebar layout
│   │   ├── firebase.js               # Firebase app initialization
│   │   ├── index.css                 # Tailwind CSS v3
│   │   └── main.jsx                  # React entry point
│   │
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── postcss.config.js
│
├── LibreChat/                        # LibreChat submodule (AI SRE command center)
├── grafana/
│   ├── dashboards/
│   │   └── server-monitoring.json    # Universal Grafana dashboard
│   └── provisioning/
│       └── dashboards/
│           └── dashboard.yml
│
├── logs/                             # Application logs (auto-created)
├── docker-compose.yml                # Prometheus + Grafana services
├── prometheus.yml                    # Prometheus scrape configuration
├── targets.json                      # Dynamic targets (auto-managed by API)
├── requirements.txt                  # Python dependencies
├── .env                              # Environment variables
├── .gitignore
├── LIBRECHAT_AGENTS.md               # LibreChat agent setup guide
├── langfuse_integration_instructions.md  # Langfuse setup guide
└── README.md
```

---

## Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    AI DevOps Monitor & Analysis Hub                       │
│                                                                            │
│  ┌──────────────┐      ┌──────────────────┐      ┌────────────────────┐  │
│  │   React UI   │◀────▶│  FastAPI Backend │◀────▶│  LibreChat (SRE)   │  │
│  │  (Firebase)  │      │   (Python 3.10)  │      │  AI Analyst Hub    │  │
│  └──────────────┘      └────────┬─────────┘      └────────────────────┘  │
│                                 │                                          │
│             ┌───────────────────┼───────────────────┐                     │
│             ▼                   ▼                   ▼                     │
│       ┌──────────┐       ┌───────────┐       ┌──────────┐                │
│       │Prometheus│       │  MongoDB  │       │ Langfuse │                │
│       └──────────┘       └───────────┘       └──────────┘                │
│             ▲                   ▲                   ▲                     │
│             │       ┌───────────┴──────┐            │                     │
│             └───────┤  LLM Service     ├────────────┘                     │
│                     │ Gemini (primary) │                                  │
│                     │ Gemma3 (fallback)│                                  │
│                     └──────────────────┘                                  │
└──────────────────────────────────────────────────────────────────────────┘
```

### Authentication Flow

```
Frontend: Firebase Auth (email/password or Google OAuth)
         ↓ Get Firebase ID Token
Backend:  Verify token with Firebase Admin SDK
         ↓ Create/retrieve user in MongoDB
         ↓ Issue JWT access token (15 min) + refresh token (7 days)
         ↓ Store session with device info (browser, OS, IP)
Frontend: Store JWT in localStorage
         ↓ Send JWT in Authorization header for all API calls
On 401:  Auto-refresh via Firebase, get new JWT
```

### Batch Monitoring Flow (Per User, every `BATCH_INTERVAL_MINUTES`)

```
1. Fetch user's Prometheus targets from MongoDB
2. Query Prometheus for metrics from those targets (range query)
3. Group metrics by instance, cap to BATCH_MAX_METRICS (default 600)
4. Build structured LLM prompt with full metric context
5. Call Gemini API → trace call in Langfuse
6. Parse JSON response: incident + anomalies + RCA
7. Store batch → incident → anomalies → RCA (all with user_id)
8. Send alerts via user's email/Slack configuration
9. Mark processing window complete (prevents duplicate analysis)
```

### Multi-User Data Isolation

Every database query includes a `user_id` filter — users can never see each other's data:

```python
# All queries automatically scoped to the authenticated user
user_filter = {"user_id": current_user.id}

db.metrics_batches.find(user_filter)
db.anomalies.find(user_filter)
db.incidents.find(user_filter)
db.targets.find(user_filter)
db.email_config.find_one(user_filter)
```

---

## API Documentation

Full interactive documentation available at http://localhost:8000/docs

### Authentication Endpoints (`/api/auth/`)

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/auth/register` | POST | No | Register with Firebase ID token + username |
| `/api/auth/login` | POST | No | Login with Firebase ID token, receive JWT |
| `/api/auth/me` | GET | JWT | Get current authenticated user |
| `/api/auth/sessions` | GET | JWT | List all active sessions with device info |
| `/api/auth/sessions/{id}` | DELETE | JWT | Revoke a specific session |
| `/api/auth/sessions/revoke-all` | POST | JWT | Revoke all sessions except current |

### Data Endpoints (all require JWT)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | System health status |
| `/stats` | GET | User's collection counts and notification status |
| `/batches` | GET | User's metrics batches (paginated) |
| `/anomalies` | GET | User's detected anomalies (paginated) |
| `/rca` | GET | User's root cause analyses |
| `/incidents` | GET | User's detected incidents |

### Configuration Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/agent/email-config` | GET / PUT | Email notification settings |
| `/api/agent/slack-config` | GET / PUT | Slack webhook settings |
| `/api/agent/test-email` | POST | Send test email |
| `/api/agent/test-slack` | POST | Send test Slack message |
| `/api/agent/targets` | GET | List user's Prometheus targets |
| `/api/agent/targets` | POST | Add a new monitoring target |
| `/api/agent/targets/{endpoint}` | DELETE | Remove a monitoring target |

### Chat / LibreChat Bridge

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat/query` | POST | Query LLM about a specific session/incident |
| `/api/chat/latest` | POST | Get AI summary of latest system health |
| `/api/chat/sessions` | GET | List user's chat sessions |
| `/api/chat/sessions/{id}` | GET | Get full chat session details |

### Langfuse Monitor

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/langfuse-monitor/watched-users` | GET | List watched Langfuse users |
| `/api/langfuse-monitor/watched-users` | POST | Add a Langfuse user to watch |
| `/api/langfuse-monitor/watched-users/{id}` | DELETE | Remove a watched user |
| `/api/langfuse-monitor/stats` | GET | Aggregate stats (traces, tokens, cost, latency) |
| `/api/langfuse-monitor/traces` | GET | Recent traces from watched users |
| `/api/langfuse-monitor/rca` | GET | RCA results ingested from Langfuse |

---

## LibreChat Analysis Hub

The integrated LibreChat instance provides a specialized **AI SRE Analyst** persona for deep infrastructure troubleshooting.

### AI SRE Tools (Actions)

The analyst connects directly to the FastAPI backend via an OpenAPI bridge:

| Tool | Description |
|------|-------------|
| `get_latest_health` | AI-generated summary of current system state across all instances |
| `list_sessions` | Browse recent monitoring incidents and Langfuse trace sessions |
| `query_chat` | Deep-dive into a specific incident by session ID — full RCA, metrics, recommendations |

### Setup

See [LIBRECHAT_AGENTS.md](LIBRECHAT_AGENTS.md) for complete agent creation and configuration instructions, including:
- Creating the AI SRE Analyst persona in the LibreChat UI
- Configuring Actions to point at the monitoring backend
- Domain whitelisting for the OpenAPI bridge
- Best practices for monitoring-specific agent prompts

---

## Langfuse Observability

Every LLM call is fully traced in Langfuse, providing complete visibility into the AI pipeline.

### What Is Traced

- **Input prompt** — full metric context sent to the LLM
- **LLM response** — raw JSON response with anomaly detections
- **Token counts** — prompt, completion, and total tokens
- **Latency** — time for each LLM call
- **Cost** — estimated API cost per analysis
- **Metadata** — user_id, batch window, model name, provider

### Langfuse Monitor Dashboard

The **LangfuseMonitor** component provides:

- **Watched Users** — Monitor external Langfuse accounts (e.g., your own services using Langfuse)
- **Trace Browser** — View recent LLM traces with timestamps, token counts, costs, and latency
- **RCA from Traces** — Trigger root cause analysis from raw Langfuse trace data
- **Auto-Refresh** — Dashboard auto-refreshes for real-time visibility

For setup instructions, see [langfuse_integration_instructions.md](langfuse_integration_instructions.md).

---

## Grafana Integration

The platform ships with a pre-configured Grafana dashboard that automatically detects metrics from different exporters.

### Features

- **Auto-Detection** — Uses OR queries to work with both Windows Exporter and Node Exporter metrics
- **Multi-Instance** — Instance dropdown for switching between monitored servers
- **Real-Time** — 5-second panel refresh
- **Pre-Provisioned** — Dashboard loads automatically via `grafana/provisioning/`

### Dashboard Panels

| Panel | Metrics |
|-------|---------|
| CPU Usage | Per-core and total CPU utilization |
| Memory | Available, used, and total RAM |
| Disk I/O | Read/write rates |
| Network | Bytes sent/received |
| Uptime | System uptime |
| Processes | Active process count |

### Access

1. Open http://localhost:3001
2. Navigate to Dashboards → Server Monitoring
3. Select instance from dropdown

---

## User Guide

### Getting Started

1. **Register** — Visit http://localhost:5173, click Register, create an account (Firebase handles auth)
2. **Add Servers** — Settings → Servers → Add Server → enter `IP:port` and a display name
3. **Configure Alerts**
   - Email: Settings → Email Config → enable, add recipients, test
   - Slack: Settings → Servers → enter webhook URL, enable, test
4. **View Monitoring Data**
   - Dashboard — overview stats
   - Metrics — raw Prometheus batches
   - Anomalies — AI-detected issues
   - RCA Results — root cause analyses
   - Langfuse Monitor — LLM trace observability
   - AI Analyst — LibreChat-powered deep dive

### Adding Prometheus Targets

**Windows Exporter:**
```powershell
# Install via Chocolatey
choco install prometheus-windows-exporter.install

# Default port: 9182
# Add in UI: <server-ip>:9182
```

**Node Exporter (Linux):**
```bash
# Download and run
wget https://github.com/prometheus/node_exporter/releases/latest/download/node_exporter-*-linux-amd64.tar.gz
tar xvfz node_exporter-*-linux-amd64.tar.gz
./node_exporter-*/node_exporter

# Default port: 9100
# Add in UI: <server-ip>:9100
```

### Session Management

- **Settings → Sessions** — View all active logins with device info (browser, OS, IP, last active)
- Revoke individual sessions or all other sessions remotely
- Current session is highlighted and protected from self-revocation

---

## Data Storage

### MongoDB Collections

| Collection | Purpose | User-Scoped |
|-----------|---------|-------------|
| `users` | User accounts | Yes |
| `metrics_batches` | Prometheus metric snapshots | Yes |
| `incidents` | AI-detected incidents | Yes |
| `anomalies` | Individual anomalies | Yes |
| `rca` | Root cause analyses | Yes |
| `targets` | Prometheus monitoring targets | Yes |
| `email_config` | Email notification settings | Yes |
| `slack_config` | Slack webhook settings | Yes |
| `chat_sessions` | AI chat history | Yes |
| `auth_sessions` | Active login sessions | Yes |
| `langfuse_traces` | Ingested Langfuse traces | Yes |
| `langfuse_watched_users` | Watched Langfuse accounts | Yes |

### Key Indexes

- `targets` — unique composite on `(user_id, endpoint)`
- `auth_sessions` — unique on `session_id`; composite on `(user_id, active)`
- `metrics_batches` — composite on `(user_id, window_start_ist_str)`
- `anomalies` — on `(user_id, created_at_ist)`
- `langfuse_traces` — unique on `trace_id`; on `(langfuse_user_id, timestamp)`
- `langfuse_watched_users` — unique composite on `(langfuse_user_id, added_by)`

---

## LLM-Powered Detection

The system uses **pure AI detection** — no threshold rules or statistical methods.

### How It Works

```
Fetch Prometheus metrics
       ↓
Group by instance, cap to BATCH_MAX_METRICS
       ↓
Build structured prompt (time window + ALL metrics)
       ↓
   Gemini API (gemini-2.5-pro)   ← primary
       ↓ (if Gemini fails)
   Gemma3 via Ollama              ← automatic fallback
       ↓
Parse JSON response for incident + anomalies + clusters
       ↓
Store + alert + trace in Langfuse
```

### Why LLM-Only?

| Approach | Traditional Thresholds | LLM-Powered (this system) |
|----------|----------------------|--------------------------|
| Configuration | Manual rules per metric | None required |
| Context | Single metric at a time | All metrics simultaneously |
| Baselines | Fixed thresholds | Learned from current data |
| Explanations | "CPU > 80%" | "CPU spike correlates with memory leak" |
| False positives | High during deployments | Low — AI understands context |

### Example LLM Response

```json
{
  "incident": {
    "title": "High Memory Usage with Disk I/O Spikes",
    "severity": "high",
    "summary": "Memory at 92% with unusual disk write patterns",
    "root_cause": "Potential memory leak causing swap usage",
    "fix_plan": {
      "immediate": ["Restart affected service", "Check application logs"],
      "prevention": ["Add memory profiling", "Set up swap alerts"]
    }
  },
  "anomalies": [
    {
      "metric": "node_memory_MemAvailable_bytes",
      "instance": "192.168.1.4:9182",
      "observed": "800MB",
      "expected": "4GB average",
      "symptom": "Memory critically low"
    }
  ]
}
```

---

## Security

### Current Implementation

- **Firebase Authentication** — Industry-standard identity provider with Google OAuth
- **Argon2 Password Hashing** — Production-grade (time_cost=3, memory_cost=65536, parallelism=4)
- **JWT Tokens** — Short-lived access tokens (15 min) + refresh tokens (7 days)
- **User Data Isolation** — All queries server-side filtered by `user_id`
- **Session Revocation** — Immediate invalidation of individual or all sessions
- **SSRF Protection** — `ALLOW_PRIVATE_TARGETS=false` blocks private IP targets in production
- **Rate Limiting** — SlowAPI: 5/min for auth, 100/min for API
- **CORS** — Configured for development ports (5173, 5174, 5175, 3000, 3080)

### Production Hardening

```bash
# 1. Generate strong JWT secret
python -c "import secrets; print(secrets.token_urlsafe(64))"

# 2. Restrict CORS to your domain
# In app/main.py:
allow_origins=["https://yourdomain.com"]

# 3. Disable private targets
ALLOW_PRIVATE_TARGETS=false

# 4. Enable rate limiting
ENABLE_RATE_LIMITING=true
```

---

## Alerting

### Email Alert Format

```
Subject: [HIGH] High Memory Usage with Disk I/O Spikes

Window: 2026-03-15 14:30 → 14:32 IST

Summary: Memory at 92% with unusual disk write patterns

Root Cause: Potential memory leak causing swap usage

Immediate Actions:
  • Restart affected service
  • Check application logs

Anomalies: 2 | Confidence: 85%
```

### Slack Alert Format

```
[HIGH] High Memory Usage with Disk I/O Spikes
Window: 2026-03-15 14:30 → 14:32 IST
Memory at 92% with unusual disk write patterns
Root Cause: Potential memory leak causing swap usage
Actions: Restart affected service, Check application logs
Anomalies: 2
```

---

## Troubleshooting

### Prometheus Targets Not Scraping

1. Check Prometheus UI: http://localhost:9099/targets
2. Ensure `targets.json` is mounted correctly in Docker
3. Verify the exporter is running on the target server
4. Check SSRF protection: `ALLOW_PRIVATE_TARGETS=true` for local IPs in dev

```bash
# Reload Prometheus config
docker-compose restart prometheus
```

### No Anomalies Detected

This is normal and means your system is healthy — the AI only alerts when it genuinely detects problems. If you expect anomalies and none appear:
1. Verify targets are being scraped in Prometheus UI
2. Check that your user account owns the correct targets (Settings → Servers)
3. Check backend logs for LLM errors

### Email/Slack Alerts Not Sending

Alerts use **per-user configuration** — not global `.env` settings.

1. Login to your account
2. Settings → Email Config or Servers → configure and enable
3. Click Test Email / Test Slack to verify
4. Check SMTP credentials and App Password for Gmail

### Langfuse Connection Reset / 401 Unauthorized

If you see "An existing connection was forcibly closed by the remote host" or 401 errors:
1. **Check .env Spaces**: Ensure there are no trailing spaces after `LANGFUSE_HOST` or `LANGFUSE_SECRET_KEY`.
2. **Restart Backend**: Run `uvicorn` again to reload the cleaned environment.
3. **Session Pooling**: v2.6.0 includes automatic connection pooling; if issues persist, check if your firewall blocks non-browser User-Agents (our client now spoofs a Chrome header).

### Frontend 401 / CORS Errors

1. Ensure backend runs on port 8000
2. Ensure frontend runs on port 5173
3. Check Firebase configuration in `frontend/src/firebase.js`
4. Verify Firebase project ID matches `FIREBASE_PROJECT_ID` in backend `.env`

### LLM Not Responding

The system automatically falls back from Gemini to Gemma3. If both fail:
1. Check `GEMINI_API_KEY` is valid and has quota
2. Verify Ollama is running: `curl http://localhost:11434/api/tags`
3. Pull the fallback model: `ollama pull gemma3:1b`

---

## Performance

### Benchmarks (2-minute batches, ~600 metrics)

| Metric | Value |
|--------|-------|
| Prometheus fetch | ~1s |
| LLM analysis (Gemini) | 2-5s |
| LLM analysis (Gemma3) | 10-20s |
| Alert delivery | 1-2s |
| **Total cycle** | **~5-20s** |
| Memory usage | ~250MB |
| Concurrent users | 20+ |

### Scaling

| Users | Recommendation |
|-------|---------------|
| 1-10 | Single server (current setup) |
| 10-50 | Add Redis for session cache |
| 50+ | Separate batch workers, load balancer |
| 100+ | Kubernetes, managed MongoDB Atlas |

---

## Dependencies

### Backend (requirements.txt)

| Package | Purpose |
|---------|---------|
| fastapi | REST framework |
| uvicorn | ASGI server |
| pymongo | MongoDB driver |
| langfuse | LLM observability |
| google-generativeai | Gemini API |
| openai | Backup LLM support |
| firebase-admin | Firebase Admin SDK |
| argon2-cffi | Password hashing |
| PyJWT | JWT token management |
| slowapi | Rate limiting |
| prometheus-fastapi-instrumentator | Prometheus metrics for the API |
| user-agents | Device detection from User-Agent headers |
| httpx | Async HTTP client |
| python-dotenv | Environment variable loading |
| email-validator | Email address validation |

### Frontend (package.json)

| Package | Purpose |
|---------|---------|
| react 19 | UI library |
| react-router-dom 7 | Client-side routing |
| firebase 12 | Authentication |
| recharts 3 | Data visualization |
| vite 7 | Build tool |
| tailwindcss 3 | Utility-first CSS |
