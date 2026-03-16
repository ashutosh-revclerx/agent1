/**
 * API Service
 * Fetch ALL database data (auto-pagination)
 */
import { auth } from '../firebase';
import { getIdToken } from 'firebase/auth';

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// You can override these from .env if needed:
const DEFAULT_PAGE_SIZE = Number(import.meta.env.VITE_PAGE_SIZE || 500);
const MAX_PAGES = Number(import.meta.env.VITE_MAX_PAGES || 500); // safety cap

/**
 * Get a fresh Firebase ID token.
 * Reads the cached token from localStorage first; on 401 it re-fetches live.
 */
async function getFirebaseToken(forceRefresh = false) {
  if (auth.currentUser) {
    const token = await getIdToken(auth.currentUser, forceRefresh);
    localStorage.setItem('token', token);
    return token;
  }
  // Fallback: try localStorage (set during login)
  return localStorage.getItem('token');
}

async function fetchJson(url, opts = {}) {
  const token = localStorage.getItem('token');
  const headers = { ...opts.headers };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  let res = await fetch(url, { ...opts, headers });

  // On 401: try a force-refresh of the Firebase ID token, then retry once
  if (res.status === 401) {
    try {
      const newToken = await getFirebaseToken(true /* forceRefresh */);
      if (newToken) {
        headers['Authorization'] = `Bearer ${newToken}`;
        res = await fetch(url, { ...opts, headers });
      }
    } catch (e) {
      // Firebase token refresh failed — likely signed out
      localStorage.removeItem('token');
      window.location.href = '/login';
      throw new Error('Session expired. Please log in again.');
    }
  }

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    let errorMessage = data.detail || `HTTP ${res.status}`;

    // Handle FastAPI validation error arrays (422)
    if (Array.isArray(data.detail)) {
      errorMessage = data.detail.map(e => `${e.loc.join('.')}: ${e.msg}`).join(', ');
    } else if (typeof data.detail === 'object') {
      errorMessage = JSON.stringify(data.detail);
    }

    throw new Error(errorMessage);
  }
  return res.json();
}


/**
 * Fetch all pages from an endpoint that supports:
 *   ?limit=<pageSize>&skip=<offset>
 * And returns either:
 *   { [key]: [...] }  OR  [...]
 */
async function fetchAllPages(endpoint, key, pageSize = DEFAULT_PAGE_SIZE) {
  const all = [];
  let skip = 0;

  // To prevent infinite loops when backend ignores skip/limit
  let lastFirstId = null;

  for (let page = 0; page < MAX_PAGES; page++) {
    const qs = new URLSearchParams({
      limit: String(pageSize),
      skip: String(skip),
    }).toString();

    const url = `${API_BASE_URL}/${endpoint}?${qs}`;
    const data = await fetchJson(url);

    const list = Array.isArray(data) ? data : data?.[key] || [];
    if (!Array.isArray(list) || list.length === 0) break;

    // Guard: if backend ignores pagination, it may return same page again
    const firstId = list?.[0]?._id ? String(list[0]._id) : null;
    if (firstId && firstId === lastFirstId) break;
    lastFirstId = firstId;

    all.push(...list);

    // If last page
    if (list.length < pageSize) break;

    skip += pageSize;
  }

  return all;
}

export const api = {
  // ============ HEALTH & STATS ============

  async getHealth() {
    return fetchJson(`${API_BASE_URL}/health`);
  },

  async getStats() {
    return fetchJson(`${API_BASE_URL}/stats`);
  },

  // ============ DATA ENDPOINTS ============

  async getPromMetrics() {
    return fetchJson(`${API_BASE_URL}/prom-metrics`);
  },

  // ✅ Updated: fetch ALL anomalies
  async getAnomalies() {
    const anomalies = await fetchAllPages("anomalies", "anomalies");
    return { anomalies };
  },

  // ✅ Updated: fetch ALL RCA results
  async getRCA() {
    const rca = await fetchAllPages("rca", "rca");
    return { rca };
  },

  // ============ CHAT ENDPOINT ============

  async chat(payload) {
    return fetchJson(`${API_BASE_URL}/chat/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  // ============ SESSION MANAGEMENT ============

  async getSessions() {
    return fetchJson(`${API_BASE_URL}/api/sessions`);
  },

  async getSessionDetails(sessionId) {
    return fetchJson(`${API_BASE_URL}/api/sessions/${sessionId}`);
  },

  async deleteSession(sessionId) {
    return fetchJson(`${API_BASE_URL}/api/sessions/${sessionId}`, {
      method: "DELETE",
    });
  },

  // ============ EMAIL CONFIGURATION ============

  async getEmailConfig() {
    return fetchJson(`${API_BASE_URL}/agent/email-config`);
  },

  async updateEmailConfig(config) {
    return fetchJson(`${API_BASE_URL}/agent/email-config`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    });
  },

  async sendTestEmail() {
    return fetchJson(`${API_BASE_URL}/agent/test-email`, { method: "POST" });
  },

  // ============ SLACK (ENV ONLY) ============

  async getSlackStatus() {
    return fetchJson(`${API_BASE_URL}/agent/slack-status`);
  },

  async sendTestSlack() {
    return fetchJson(`${API_BASE_URL}/agent/test-slack`, { method: "POST" });
  },

  // ============ SERVER / TARGET MANAGEMENT ============

  async getTargets() {
    return fetchJson(`${API_BASE_URL}/agent/targets`);
  },

  async addTarget(target) {
    return fetchJson(`${API_BASE_URL}/agent/targets`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(target),
    });
  },

  async removeTarget(endpoint) {
    return fetchJson(
      `${API_BASE_URL}/agent/targets/${encodeURIComponent(endpoint)}`,
      { method: "DELETE" }
    );
  },

  // ============ SLACK CONFIGURATION ============

  async getSlackConfig() {
    return fetchJson(`${API_BASE_URL}/agent/slack-config`);
  },

  async updateSlackConfig(config) {
    return fetchJson(`${API_BASE_URL}/agent/slack-config`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    });
  },

  // ============ LANGFUSE STATUS ============

  async getLangfuseStatus() {
    return fetchJson(`${API_BASE_URL}/langfuse/status`);
  },

  // ============ LANGFUSE MONITOR ============

  async getLangfuseWatchedUsers() {
    return fetchJson(`${API_BASE_URL}/api/langfuse-monitor/watched-users`);
  },

  async addLangfuseWatchedUser(langfuse_user_id, label) {
    return fetchJson(`${API_BASE_URL}/api/langfuse-monitor/watched-users`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ langfuse_user_id, label: label || langfuse_user_id }),
    });
  },

  async removeLangfuseWatchedUser(langfuse_user_id) {
    return fetchJson(
      `${API_BASE_URL}/api/langfuse-monitor/watched-users/${encodeURIComponent(langfuse_user_id)}`,
      { method: "DELETE" }
    );
  },

  async getLangfuseStats(hours = 24, langfuse_user_id = null) {
    const params = new URLSearchParams({ hours });
    if (langfuse_user_id) params.append("langfuse_user_id", langfuse_user_id);
    return fetchJson(`${API_BASE_URL}/api/langfuse-monitor/stats?${params}`);
  },

  async getLangfuseTraces(hours = 24, langfuse_user_id = null, limit = 50) {
    const params = new URLSearchParams({ hours, limit });
    if (langfuse_user_id) params.append("langfuse_user_id", langfuse_user_id);
    return fetchJson(`${API_BASE_URL}/api/langfuse-monitor/traces?${params}`);
  },

  async getLangfuseRCA(hours = 24, langfuse_user_id = null) {
    const params = new URLSearchParams({ hours });
    if (langfuse_user_id) params.append("langfuse_user_id", langfuse_user_id);
    return fetchJson(`${API_BASE_URL}/api/langfuse-monitor/rca?${params}`);
  },

  async runLangfuseRCA(hours = 1, langfuse_user_id = null) {
    const params = new URLSearchParams({ hours });
    if (langfuse_user_id) params.append("langfuse_user_id", langfuse_user_id);
    return fetchJson(`${API_BASE_URL}/api/langfuse-monitor/rca/run?${params}`, {
      method: "POST",
    });
  },



  async getBatches() {
    const batches = await fetchAllPages("batches", "batches");
    return { batches };
  },

  async getIncidents() {
    const incidents = await fetchAllPages("incidents", "incidents");
    return { incidents };
  },

  // ============ AUTHENTICATION ============

  async register(username, email, password) {
    const res = await fetch(`${API_BASE_URL}/api/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, email, password })
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'Registration failed');
    }

    const data = await res.json();
    localStorage.setItem('token', data.access_token);
    if (data.refresh_token) {
      localStorage.setItem('refreshToken', data.refresh_token);
    }
    return data;
  },

  async login(username, password) {
    const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'Login failed');
    }

    const data = await res.json();
    localStorage.setItem('token', data.access_token);
    if (data.refresh_token) {
      localStorage.setItem('refreshToken', data.refresh_token);
    }
    return data;
  },

  async logout() {
    const refreshToken = localStorage.getItem('refreshToken');

    if (refreshToken) {
      try {
        await fetchJson(`${API_BASE_URL}/api/auth/logout`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken })
        });
      } catch (error) {
        // Ignore errors during logout
        console.error('Logout error:', error);
      }
    }

    localStorage.removeItem('token');
    localStorage.removeItem('refreshToken');
  },


  async getCurrentUser() {
    return fetchJson(`${API_BASE_URL}/api/auth/me`);
  },

  // ============ SESSION MANAGEMENT (AUTH) ============

  async getAuthSessions() {
    return fetchJson(`${API_BASE_URL}/api/auth/sessions`);
  },

  async revokeSession(sessionId) {
    return fetchJson(`${API_BASE_URL}/api/auth/sessions/${sessionId}`, {
      method: 'DELETE'
    });
  },

  async revokeAllSessions(keepCurrent = true) {
    return fetchJson(`${API_BASE_URL}/api/auth/sessions/revoke-all?keep_current=${keepCurrent}`, {
      method: 'POST'
    });
  },

  // ============ ALERT CONFIGURATION ============

  async getEmailConfig() {
    return fetchJson(`${API_BASE_URL}/agent/email-config`);
  },

  async updateEmailConfig(config) {
    return fetchJson(`${API_BASE_URL}/agent/email-config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config)
    });
  },

  async sendTestEmail() {
    return fetchJson(`${API_BASE_URL}/agent/test-email`, { method: 'POST' });
  },

  async getSlackConfig() {
    return fetchJson(`${API_BASE_URL}/agent/slack-config`);
  },

  async updateSlackConfig(config) {
    return fetchJson(`${API_BASE_URL}/agent/slack-config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config)
    });
  },

  async sendTestSlack() {
    return fetchJson(`${API_BASE_URL}/agent/test-slack`, { method: 'POST' });
  },

  // ============ GRAFANA INTEGRATION ============

  async getGrafanaUrl(instance) {
    return fetchJson(`${API_BASE_URL}/grafana-url?instance=${encodeURIComponent(instance)}`);
  },
};
