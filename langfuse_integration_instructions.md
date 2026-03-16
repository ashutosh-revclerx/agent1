# Langfuse Polling Integration — Implementation Instructions

## Overview
Add Langfuse as a second monitoring source alongside Prometheus. A background task polls Langfuse every 2 minutes for new traces from watched user IDs and stores them in MongoDB. A new API endpoint and UI page display this data.

## Key Patterns From Existing Codebase
- **MongoDB**: Synchronous PyMongo via `get_db()` — NOT async motor. Wrap DB calls in `run_in_executor`
- **Config**: Plain `os.getenv()` in `app/core/config.py` — no Settings class
- **Background tasks**: `asyncio.create_task()` with `while True` + `asyncio.sleep()` inside `lifespan`
- **Logging**: `from app.core.logging import logger`
- **Router**: Registered via `app/api/router.py` which is included in `main.py`
- **Langfuse credentials**: Already exist in `config.py` as `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`

---

## Files To Create

### 1. `app/services/langfuse_ingestion_service.py`
```python
"""
Langfuse Ingestion Service
Polls Langfuse every 2 minutes for new traces from watched user IDs
and stores them in MongoDB (langfuse_traces collection).
"""
import asyncio
import requests
from datetime import datetime, timedelta, timezone

from app.core.config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
from app.services.mongodb_service import get_db
from app.core.logging import logger

POLL_INTERVAL_SECONDS = 120  # 2 minutes


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
            "timestamp": trace["timestamp"],
            "latency_s": trace.get("latency"),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cost_usd": round(float(trace.get("totalCost") or 0.0), 6),
            "model": model,
            "session_id": trace.get("sessionId"),
            "status": status,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            db.langfuse_traces.insert_one(doc)
            ingested += 1
        except Exception as e:
            logger.error(f"[Langfuse] Failed to insert trace {trace_id}: {e}")

    logger.info(f"[Langfuse] user={langfuse_user_id} | found={len(traces)} | new={ingested}")
    return ingested


async def poll_langfuse():
    """
    Background task: polls Langfuse every 2 minutes.
    Matches the pattern used by BatchMonitor in main.py.
    """
    logger.info("[Langfuse] Polling service started (interval=2min)")
    while True:
        try:
            loop = asyncio.get_event_loop()
            watched = await loop.run_in_executor(None, _get_watched_user_ids_sync)

            if not watched:
                logger.debug("[Langfuse] No watched users, skipping poll")
            else:
                for user_id in watched:
                    await loop.run_in_executor(None, _ingest_for_user_sync, user_id)

        except Exception as e:
            logger.error(f"[Langfuse] Poll loop error: {e}")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)
```

---

### 2. `app/api/endpoints/langfuse_monitor.py`
```python
"""
Langfuse Monitor Endpoints
CRUD for watched users + read traces/stats from MongoDB.
Follows the same patterns as other endpoints in app/api/endpoints/.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.services.mongodb_service import get_db
from app.core.logging import logger

# Match auth import pattern from other endpoint files in your project
# e.g. from app.core.auth import get_current_user
# Replace the import below with whatever your project uses:
from app.core.auth import get_current_user

router = APIRouter(prefix="/langfuse-monitor", tags=["langfuse-monitor"])


class WatchedUserIn(BaseModel):
    langfuse_user_id: str
    label: Optional[str] = None


# ── Watched Users ──────────────────────────────────────────────────────────────

@router.get("/watched-users")
def get_watched_users(current_user=Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    docs = list(db.langfuse_watched_users.find({}, {"_id": 0}))
    return {"users": docs}


@router.post("/watched-users")
def add_watched_user(body: WatchedUserIn, current_user=Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    existing = db.langfuse_watched_users.find_one(
        {"langfuse_user_id": body.langfuse_user_id}
    )
    if existing:
        raise HTTPException(status_code=400, detail="User already being watched")

    db.langfuse_watched_users.insert_one({
        "langfuse_user_id": body.langfuse_user_id,
        "label": body.label or body.langfuse_user_id,
        "added_at": datetime.now(timezone.utc).isoformat(),
        "added_by": str(current_user.get("_id", "")),
    })
    return {"message": f"Now watching {body.langfuse_user_id}"}


@router.delete("/watched-users/{langfuse_user_id:path}")
def remove_watched_user(langfuse_user_id: str, current_user=Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    result = db.langfuse_watched_users.delete_one(
        {"langfuse_user_id": langfuse_user_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Watched user not found")
    return {"message": f"Stopped watching {langfuse_user_id}"}


# ── Stats & Traces ─────────────────────────────────────────────────────────────

@router.get("/stats")
def get_stats(
    hours: int = Query(default=24, ge=1, le=168),
    langfuse_user_id: Optional[str] = Query(default=None),
    current_user=Depends(get_current_user),
):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    query = {"timestamp": {"$gte": since}}
    if langfuse_user_id:
        query["langfuse_user_id"] = langfuse_user_id

    traces = list(db.langfuse_traces.find(query, {"_id": 0}))

    total_input = sum(t.get("input_tokens", 0) for t in traces)
    total_output = sum(t.get("output_tokens", 0) for t in traces)
    total_cost = sum(t.get("cost_usd", 0) for t in traces)
    latencies = [t["latency_s"] for t in traces if t.get("latency_s")]
    errors = sum(1 for t in traces if t.get("status") == "error")

    models: dict = {}
    users: dict = {}
    for t in traces:
        m = t.get("model")
        u = t.get("langfuse_user_id")
        if m:
            models[m] = models.get(m, 0) + 1
        if u:
            users[u] = users.get(u, 0) + 1

    return {
        "total_traces": len(traces),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_input + total_output,
        "total_cost_usd": round(total_cost, 6),
        "avg_latency_s": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
        "error_count": errors,
        "models_used": models,
        "active_users": users,
        "hours_window": hours,
    }


@router.get("/traces")
def get_traces(
    hours: int = Query(default=24, ge=1, le=168),
    langfuse_user_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user=Depends(get_current_user),
):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    query = {"timestamp": {"$gte": since}}
    if langfuse_user_id:
        query["langfuse_user_id"] = langfuse_user_id

    traces = list(
        db.langfuse_traces.find(query, {"_id": 0})
        .sort("timestamp", -1)
        .limit(limit)
    )
    return {"traces": traces, "count": len(traces)}
```

---

## Files To Modify

### 3. `app/api/router.py` — Register the new router
Add these two lines alongside the other router imports and includes:

```python
# ADD this import with the other endpoint imports:
from app.api.endpoints.langfuse_monitor import router as langfuse_monitor_router

# ADD this include with the other app.include_router() calls:
api_router.include_router(langfuse_monitor_router)
```

---

### 4. `app/main.py` — Start the polling task

**Step 1** — Add import at the top with other service imports:
```python
from app.services.langfuse_ingestion_service import poll_langfuse
```

**Step 2** — Inside the `lifespan` function, add `asyncio.create_task(poll_langfuse())`
right after `monitor_manager.start()`. The section should look like this:

```python
    # Start multi-user monitor manager
    monitor_manager.start()
    await monitor_manager.refresh_monitors()  # Initial refresh

    # ← ADD THIS LINE:
    asyncio.create_task(poll_langfuse())
    logger.info("[Langfuse] Polling task started")
```

**Step 3** — Inside the `lifespan` function, add MongoDB indexes for the two new
collections. Add these lines right after the existing `db.alert_windows.create_index` calls:

```python
            # Langfuse ingestion indexes
            db.langfuse_traces.create_index("trace_id", unique=True)
            db.langfuse_traces.create_index([("langfuse_user_id", 1), ("timestamp", -1)])
            db.langfuse_traces.create_index("timestamp")
            db.langfuse_watched_users.create_index("langfuse_user_id", unique=True)
```

---

### 5. `app/core/config.py` — No changes needed
`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` are already defined.
Make sure your `.env` has the correct values:

```env
LANGFUSE_PUBLIC_KEY=pk-lf-your-public-key-here
LANGFUSE_SECRET_KEY=sk-lf-your-secret-key-here
LANGFUSE_HOST=https://cloud.langfuse.com
```

---

### 6. `frontend/src/components/LangfuseMonitor.jsx` — Create new file
```jsx
import { useState, useEffect } from "react";
import api from "../services/api";

export default function LangfuseMonitor() {
  const [stats, setStats] = useState(null);
  const [traces, setTraces] = useState([]);
  const [watchedUsers, setWatchedUsers] = useState([]);
  const [hours, setHours] = useState(24);
  const [selectedUser, setSelectedUser] = useState("");
  const [newUserId, setNewUserId] = useState("");
  const [newUserLabel, setNewUserLabel] = useState("");
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);

  useEffect(() => { fetchWatchedUsers(); }, []);
  useEffect(() => { fetchData(); }, [hours, selectedUser]);

  const fetchWatchedUsers = async () => {
    try {
      const res = await api.get("/langfuse-monitor/watched-users");
      setWatchedUsers(res.data.users);
    } catch (err) {
      console.error("Failed to fetch watched users", err);
    }
  };

  const fetchData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ hours });
      if (selectedUser) params.append("langfuse_user_id", selectedUser);
      const [statsRes, tracesRes] = await Promise.all([
        api.get(`/langfuse-monitor/stats?${params}`),
        api.get(`/langfuse-monitor/traces?${params}&limit=50`),
      ]);
      setStats(statsRes.data);
      setTraces(tracesRes.data.traces);
    } catch (err) {
      console.error("Failed to fetch Langfuse data", err);
    } finally {
      setLoading(false);
    }
  };

  const addWatchedUser = async () => {
    if (!newUserId.trim()) return;
    setAdding(true);
    try {
      await api.post("/langfuse-monitor/watched-users", {
        langfuse_user_id: newUserId.trim(),
        label: newUserLabel.trim() || newUserId.trim(),
      });
      setNewUserId("");
      setNewUserLabel("");
      await fetchWatchedUsers();
    } catch (err) {
      alert(err.response?.data?.detail || "Failed to add user");
    } finally {
      setAdding(false);
    }
  };

  const removeWatchedUser = async (userId) => {
    if (!confirm(`Stop watching "${userId}"?`)) return;
    try {
      await api.delete(`/langfuse-monitor/watched-users/${encodeURIComponent(userId)}`);
      await fetchWatchedUsers();
      if (selectedUser === userId) setSelectedUser("");
    } catch (err) {
      alert("Failed to remove user");
    }
  };

  const statCards = stats ? [
    { label: "Total Traces",   value: stats.total_traces,                    color: "blue"   },
    { label: "Total Tokens",   value: stats.total_tokens.toLocaleString(),   color: "purple" },
    { label: "Total Cost",     value: `$${stats.total_cost_usd}`,            color: "green"  },
    { label: "Avg Latency",    value: `${stats.avg_latency_s}s`,             color: "yellow" },
    { label: "Input Tokens",   value: stats.total_input_tokens.toLocaleString(), color: "indigo"},
    { label: "Output Tokens",  value: stats.total_output_tokens.toLocaleString(), color: "pink" },
    { label: "Errors",         value: stats.error_count,                     color: stats.error_count > 0 ? "red" : "green" },
    { label: "Active Users",   value: Object.keys(stats.active_users).length, color: "teal" },
  ] : [];

  return (
    <div className="p-6 space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-white">🤖 LLM Monitor (Langfuse)</h1>
        <div className="flex gap-2 flex-wrap">
          <select value={selectedUser} onChange={e => setSelectedUser(e.target.value)}
            className="bg-gray-800 text-white border border-gray-600 rounded px-3 py-1 text-sm">
            <option value="">All Users</option>
            {watchedUsers.map(u => (
              <option key={u.langfuse_user_id} value={u.langfuse_user_id}>{u.label}</option>
            ))}
          </select>
          <select value={hours} onChange={e => setHours(Number(e.target.value))}
            className="bg-gray-800 text-white border border-gray-600 rounded px-3 py-1 text-sm">
            <option value={1}>Last 1h</option>
            <option value={6}>Last 6h</option>
            <option value={24}>Last 24h</option>
            <option value={72}>Last 3d</option>
            <option value={168}>Last 7d</option>
          </select>
          <button onClick={fetchData}
            className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-sm">
            Refresh
          </button>
        </div>
      </div>

      {/* Watched Users Management */}
      <div className="bg-gray-800 rounded-lg p-4 space-y-3">
        <h2 className="text-white font-semibold">Watched Langfuse Users</h2>
        <div className="flex gap-2 flex-wrap">
          {watchedUsers.length === 0 && (
            <span className="text-gray-400 text-sm">No users being watched yet</span>
          )}
          {watchedUsers.map(u => (
            <div key={u.langfuse_user_id}
              className="flex items-center gap-2 bg-gray-700 rounded-full px-3 py-1">
              <span className="text-sm text-white">{u.label}</span>
              {u.label !== u.langfuse_user_id && (
                <span className="text-xs text-gray-400">({u.langfuse_user_id})</span>
              )}
              <button onClick={() => removeWatchedUser(u.langfuse_user_id)}
                className="text-red-400 hover:text-red-300 text-xs ml-1">✕</button>
            </div>
          ))}
        </div>
        <div className="flex gap-2 pt-1 flex-wrap">
          <input type="text" value={newUserId} onChange={e => setNewUserId(e.target.value)}
            placeholder="Langfuse userId  (e.g. contract management agent)"
            className="bg-gray-700 text-white border border-gray-600 rounded px-3 py-1 text-sm flex-1 min-w-48" />
          <input type="text" value={newUserLabel} onChange={e => setNewUserLabel(e.target.value)}
            placeholder="Label (optional)"
            className="bg-gray-700 text-white border border-gray-600 rounded px-3 py-1 text-sm w-36" />
          <button onClick={addWatchedUser} disabled={adding || !newUserId.trim()}
            className="bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white px-4 py-1 rounded text-sm">
            {adding ? "Adding..." : "+ Watch"}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-gray-400 py-8 text-center">Loading LLM metrics...</div>
      ) : (
        <>
          {/* Stat Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {statCards.map(({ label, value, color }) => (
              <div key={label} className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <p className="text-gray-400 text-sm">{label}</p>
                <p className={`text-${color}-400 text-2xl font-bold mt-1`}>{value}</p>
              </div>
            ))}
          </div>

          {/* Models Used */}
          {stats && Object.keys(stats.models_used).length > 0 && (
            <div className="bg-gray-800 rounded-lg p-4">
              <h2 className="text-white font-semibold mb-3">Models Used</h2>
              <div className="flex gap-2 flex-wrap">
                {Object.entries(stats.models_used).map(([model, count]) => (
                  <span key={model}
                    className="bg-purple-900 text-purple-200 px-3 py-1 rounded-full text-sm">
                    {model}: {count} calls
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Traces Table */}
          <div className="bg-gray-800 rounded-lg p-4">
            <h2 className="text-white font-semibold mb-3">
              Recent Traces ({traces.length})
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-gray-300">
                <thead>
                  <tr className="text-gray-500 border-b border-gray-700 text-left">
                    <th className="py-2 pr-4">Name</th>
                    <th className="py-2 pr-4">User</th>
                    <th className="py-2 pr-4">Model</th>
                    <th className="py-2 pr-4 text-right">Tokens</th>
                    <th className="py-2 pr-4 text-right">Cost</th>
                    <th className="py-2 pr-4 text-right">Latency</th>
                    <th className="py-2 pr-4">Status</th>
                    <th className="py-2">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {traces.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="py-8 text-center text-gray-500">
                        No traces yet. Add a watched user above and wait up to 2 minutes.
                      </td>
                    </tr>
                  ) : traces.map(trace => (
                    <tr key={trace.trace_id}
                      className="border-b border-gray-700 hover:bg-gray-750">
                      <td className="py-2 pr-4 text-blue-400 text-xs font-mono truncate max-w-32">
                        {trace.name || "—"}
                      </td>
                      <td className="py-2 pr-4 text-xs truncate max-w-28">
                        {trace.langfuse_user_id}
                      </td>
                      <td className="py-2 pr-4 text-xs text-purple-400">
                        {trace.model || "—"}
                      </td>
                      <td className="py-2 pr-4 text-right">
                        {(trace.total_tokens || 0).toLocaleString()}
                      </td>
                      <td className="py-2 pr-4 text-right text-green-400">
                        ${trace.cost_usd}
                      </td>
                      <td className="py-2 pr-4 text-right text-yellow-400">
                        {trace.latency_s ? `${trace.latency_s}s` : "—"}
                      </td>
                      <td className="py-2 pr-4">
                        <span className={`px-2 py-0.5 rounded text-xs ${
                          trace.status === "error"
                            ? "bg-red-900 text-red-300"
                            : "bg-green-900 text-green-300"
                        }`}>
                          {trace.status}
                        </span>
                      </td>
                      <td className="py-2 text-xs text-gray-500 whitespace-nowrap">
                        {new Date(trace.timestamp).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
```

---

### 7. `frontend/src/App.jsx` — Add route
```jsx
// ADD import:
import LangfuseMonitor from "./components/LangfuseMonitor";

// ADD route alongside existing routes:
<Route path="/langfuse" element={<ProtectedRoute><LangfuseMonitor /></ProtectedRoute>} />
```

---

### 8. `frontend/src/components/Navbar.jsx` — Add nav link
Add this alongside your existing nav links (exact JSX depends on your Navbar structure):
```jsx
<NavLink to="/langfuse">🤖 LLM Monitor</NavLink>
```

---

## New MongoDB Collections (Auto-created on first use)

| Collection | Purpose |
|---|---|
| `langfuse_watched_users` | Stores which Langfuse userIds to poll |
| `langfuse_traces` | Stores ingested traces from Langfuse |

---

## How to Verify It Works

1. Start the backend — you should see in logs:
   ```
   [Langfuse] Polling service started (interval=2min)
   ```

2. Open the UI → LLM Monitor page

3. Add a watched user: type `contract management agent` → click **+ Watch**

4. Wait up to 2 minutes

5. Logs should show:
   ```
   [Langfuse] user=contract management agent | found=3 | new=3
   ```

6. Click **Refresh** — traces appear in the table

---

## Important Notes

- `get_current_user` import in `langfuse_monitor.py` — check how other endpoint
  files in `app/api/endpoints/` import auth and match that exact pattern
- The `current_user` object shape (dict vs object) should match what other endpoints
  use — adjust `str(current_user.get("_id", ""))` if your user object uses `.id` instead
- `run_in_executor` is used in the polling service because `get_db()` returns a
  synchronous PyMongo client, matching the existing pattern in `main.py`
