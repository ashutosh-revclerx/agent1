import { useState, useEffect } from "react";
import { api } from "../services/api";

const SEV_COLORS = {
  critical: "bg-red-100 text-red-800 border-red-200",
  high: "bg-orange-100 text-orange-800 border-orange-200",
  medium: "bg-yellow-100 text-yellow-800 border-yellow-200",
  low: "bg-blue-100 text-blue-800 border-blue-200",
};

export default function LangfuseMonitor() {
  const [stats, setStats] = useState(null);
  const [traces, setTraces] = useState([]);
  const [rcaResults, setRcaResults] = useState([]);
  const [watchedUsers, setWatchedUsers] = useState([]);
  const [hours, setHours] = useState(24);
  const [selectedUser, setSelectedUser] = useState("");
  const [newUserId, setNewUserId] = useState("");
  const [newUserLabel, setNewUserLabel] = useState("");
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [runningRca, setRunningRca] = useState(false);
  const [isAutoRefresh, setIsAutoRefresh] = useState(true);

  // Chat modal
  const [chatOpen, setChatOpen] = useState(false);
  const [activeRca, setActiveRca] = useState(null);

  useEffect(() => { fetchWatchedUsers(); }, []);
  
  useEffect(() => { 
    fetchData(true); 
    let interval;
    if (isAutoRefresh) {
      interval = setInterval(() => {
        fetchData(false);
      }, 30000); // 30 seconds
    }
    return () => clearInterval(interval);
  }, [hours, selectedUser, isAutoRefresh]);


  const fetchWatchedUsers = async () => {
    try {
      const res = await api.getLangfuseWatchedUsers();
      setWatchedUsers(res.users || []);
    } catch (err) {
      console.error("Failed to fetch watched users", err);
    }
  };

  const fetchData = async (showLoading = true) => {
    if (showLoading) setLoading(true);
    try {
      const [statsRes, tracesRes, rcaRes] = await Promise.all([
        api.getLangfuseStats(hours, selectedUser || null),
        api.getLangfuseTraces(hours, selectedUser || null, 50),
        api.getLangfuseRCA(hours, selectedUser || null),
      ]);
      setStats(statsRes);
      setTraces(tracesRes.traces || []);
      setRcaResults(rcaRes.rca || []);
    } catch (err) {
      console.error("Failed to fetch Langfuse data", err);
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  const addWatchedUser = async () => {
    if (!newUserId.trim()) return;
    setAdding(true);
    try {
      await api.addLangfuseWatchedUser(newUserId.trim(), newUserLabel.trim() || newUserId.trim());
      setNewUserId("");
      setNewUserLabel("");
      await fetchWatchedUsers();
      // Immediately fetch data so new traces appear right away
      await fetchData(false);
    } catch (err) {
      alert(err.message || "Failed to add user");
    } finally {
      setAdding(false);
    }
  };


  const removeWatchedUser = async (userId) => {
    if (!confirm(`Stop watching "${userId}"?`)) return;
    try {
      await api.removeLangfuseWatchedUser(userId);
      await fetchWatchedUsers();
      if (selectedUser === userId) setSelectedUser("");
    } catch (err) {
      alert("Failed to remove user");
    }
  };

  const runRcaAnalysis = async () => {
    setRunningRca(true);
    try {
      const res = await api.runLangfuseRCA(
        Math.min(hours, 24),
        selectedUser || null
      );
      if (res.rca) {
        setRcaResults(prev => [res.rca, ...prev]);
      } else {
        alert(res.message || "No traces to analyze");
      }
    } catch (err) {
      alert(err.message || "RCA analysis failed");
    } finally {
      setRunningRca(false);
    }
  };

  const statCards = stats ? [
    { label: "Total Traces",  value: stats.total_traces,                         color: "text-blue-600"   },
    { label: "Total Tokens",  value: (stats.total_tokens || 0).toLocaleString(), color: "text-purple-600" },
    { label: "Total Cost",    value: `$${stats.total_cost_usd}`,                 color: "text-green-600"  },
    { label: "Avg Latency",   value: `${stats.avg_latency_s}s`,                  color: "text-yellow-600" },
    { label: "Input Tokens",  value: (stats.total_input_tokens || 0).toLocaleString(),  color: "text-indigo-600" },
    { label: "Output Tokens", value: (stats.total_output_tokens || 0).toLocaleString(), color: "text-pink-600"   },
    { label: "Errors",        value: stats.error_count,                          color: stats.error_count > 0 ? "text-red-600" : "text-green-600" },
    { label: "Active Users",  value: Object.keys(stats.active_users || {}).length, color: "text-teal-600" },
  ] : [];

  return (
    <div className="space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">🤖 LLM Monitor</h1>
          <p className="text-sm text-gray-500 mt-1">Langfuse trace ingestion & analytics</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <select value={selectedUser} onChange={e => setSelectedUser(e.target.value)}
            className="bg-white text-gray-800 border border-gray-300 rounded-lg px-3 py-2 text-sm shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500">
            <option value="">All Users</option>
            {watchedUsers.map(u => (
              <option key={u.langfuse_user_id} value={u.langfuse_user_id}>{u.label}</option>
            ))}
          </select>
          <select value={hours} onChange={e => setHours(Number(e.target.value))}
            className="bg-white text-gray-800 border border-gray-300 rounded-lg px-3 py-2 text-sm shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500">
            <option value={1}>Last 1h</option>
            <option value={6}>Last 6h</option>
            <option value={24}>Last 24h</option>
            <option value={72}>Last 3d</option>
            <option value={168}>Last 7d</option>
          </select>
          <label className="flex items-center gap-2 text-sm text-gray-700 bg-white border border-gray-300 rounded-lg px-3 py-2 shadow-sm cursor-pointer hover:bg-gray-50">
            <input type="checkbox" checked={isAutoRefresh} onChange={e => setIsAutoRefresh(e.target.checked)} className="rounded text-blue-600 focus:ring-blue-500" />
            Auto-refresh
          </label>
          <button onClick={() => fetchData(true)}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-semibold transition-colors shadow-sm">
            Refresh
          </button>
        </div>
      </div>

      {/* Watched Users Management */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 space-y-3">
        <h2 className="text-gray-900 font-semibold">Watched Langfuse Users</h2>
        <div className="flex gap-2 flex-wrap">
          {watchedUsers.length === 0 && (
            <span className="text-gray-400 text-sm">No users being watched yet</span>
          )}
          {watchedUsers.map(u => (
            <div key={u.langfuse_user_id}
              className="flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-full px-3 py-1">
              <span className="text-sm text-blue-800 font-medium">{u.label}</span>
              {u.label !== u.langfuse_user_id && (
                <span className="text-xs text-blue-500">({u.langfuse_user_id})</span>
              )}
              <button onClick={() => removeWatchedUser(u.langfuse_user_id)}
                className="text-red-400 hover:text-red-600 text-xs ml-1 font-bold">✕</button>
            </div>
          ))}
        </div>
        <div className="flex gap-2 pt-1 flex-wrap">
          <input type="text" value={newUserId} onChange={e => setNewUserId(e.target.value)}
            placeholder="Langfuse userId  (e.g. contract management agent)"
            className="bg-gray-50 text-gray-800 border border-gray-300 rounded-lg px-3 py-2 text-sm flex-1 min-w-48 focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
          <input type="text" value={newUserLabel} onChange={e => setNewUserLabel(e.target.value)}
            placeholder="Label (optional)"
            className="bg-gray-50 text-gray-800 border border-gray-300 rounded-lg px-3 py-2 text-sm w-36 focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
          <button onClick={addWatchedUser} disabled={adding || !newUserId.trim()}
            className="bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-semibold transition-colors shadow-sm">
            {adding ? "Adding..." : "+ Watch"}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-10 w-10 border-2 border-blue-200 border-t-blue-600" />
        </div>
      ) : (
        <>
          {/* Stat Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {statCards.map(({ label, value, color }) => (
              <div key={label} className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
                <p className="text-gray-500 text-sm">{label}</p>
                <p className={`${color} text-2xl font-bold mt-1`}>{value}</p>
              </div>
            ))}
          </div>

          {/* Models Used */}
          {stats && Object.keys(stats.models_used || {}).length > 0 && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
              <h2 className="text-gray-900 font-semibold mb-3">Models Used</h2>
              <div className="flex gap-2 flex-wrap">
                {Object.entries(stats.models_used).map(([model, count]) => (
                  <span key={model}
                    className="bg-purple-50 text-purple-700 border border-purple-200 px-3 py-1 rounded-full text-sm font-medium">
                    {model}: {count} calls
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* ── RCA Analysis Section ─────────────────────────────────── */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-gray-900 font-semibold">🔍 RCA Analysis</h2>
                <p className="text-xs text-gray-500 mt-0.5">LLM-powered root cause analysis of trace anomalies</p>
              </div>
              <button onClick={runRcaAnalysis} disabled={runningRca}
                className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-semibold transition-colors shadow-sm">
                {runningRca ? "Analyzing..." : "Run Analysis"}
              </button>
            </div>

            {rcaResults.length === 0 ? (
              <div className="text-center py-6 text-gray-400 text-sm">
                No RCA results yet. Click <strong>Run Analysis</strong> or wait for the next poll cycle.
              </div>
            ) : (
              <div className="space-y-3">
                {rcaResults.map((rca, idx) => (
                  <RcaCard key={rca.timestamp || idx} rca={rca} onAsk={() => { setActiveRca(rca); setChatOpen(true); }} />
                ))}
              </div>
            )}
          </div>

          {/* Traces Table */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
            <h2 className="text-gray-900 font-semibold mb-3">
              Recent Traces ({traces.length})
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-gray-700">
                <thead>
                  <tr className="text-gray-500 border-b border-gray-200 text-left">
                    <th className="py-2 pr-4 font-medium">Name</th>
                    <th className="py-2 pr-4 font-medium">User</th>
                    <th className="py-2 pr-4 font-medium">Model</th>
                    <th className="py-2 pr-4 text-right font-medium">Tokens</th>
                    <th className="py-2 pr-4 text-right font-medium">Cost</th>
                    <th className="py-2 pr-4 text-right font-medium">Latency</th>
                    <th className="py-2 pr-4 font-medium">Status</th>
                    <th className="py-2 font-medium">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {traces.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="py-8 text-center text-gray-400">
                        No traces yet. Add a watched user above and wait up to 2 minutes.
                      </td>
                    </tr>
                  ) : traces.map(trace => (
                    <tr key={trace.trace_id}
                      className="border-b border-gray-100 hover:bg-blue-50/50 transition-colors">
                      <td className="py-2.5 pr-4 text-blue-600 text-xs font-mono truncate max-w-32">
                        {trace.name || "—"}
                      </td>
                      <td className="py-2.5 pr-4 text-xs truncate max-w-28">
                        {trace.langfuse_user_id}
                      </td>
                      <td className="py-2.5 pr-4 text-xs text-purple-600 font-medium">
                        {trace.model || "—"}
                      </td>
                      <td className="py-2.5 pr-4 text-right">
                        {(trace.total_tokens || 0).toLocaleString()}
                      </td>
                      <td className="py-2.5 pr-4 text-right text-green-600 font-medium">
                        ${trace.cost_usd}
                      </td>
                      <td className="py-2.5 pr-4 text-right text-yellow-600">
                        {trace.latency_s ? `${trace.latency_s}s` : "—"}
                      </td>
                      <td className="py-2.5 pr-4">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                          trace.status === "error"
                            ? "bg-red-100 text-red-700"
                            : "bg-green-100 text-green-700"
                        }`}>
                          {trace.status}
                        </span>
                      </td>
                      <td className="py-2.5 text-xs text-gray-500 whitespace-nowrap">
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

      {/* Chat Modal */}
      {chatOpen && activeRca && (
        <ChatModal rca={activeRca} onClose={() => setChatOpen(false)} />
      )}
    </div>
  );
}


/* ---------- RCA Card ---------- */

function RcaCard({ rca, onAsk }) {
  const anomalyCount = (rca.anomalies || []).length;
  const healthScore = rca.health_score ?? 100;
  const healthColor = healthScore >= 80 ? "text-green-600" : healthScore >= 50 ? "text-yellow-600" : "text-red-600";

  return (
    <div className="bg-white border border-blue-100 rounded-xl p-5 hover:shadow-sm transition-shadow">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="px-2.5 py-1 rounded-full text-xs font-bold border bg-blue-50 text-blue-800 border-blue-200">
              RCA
            </span>
            <span className={`text-lg font-bold ${healthColor}`}>
              {healthScore}/100
            </span>
            <span className="text-xs text-gray-400">health score</span>
            {anomalyCount > 0 && (
              <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
                {anomalyCount} anomal{anomalyCount === 1 ? "y" : "ies"}
              </span>
            )}
          </div>

          {rca.summary && (
            <p className="text-sm text-gray-800 mt-3 bg-blue-50 border border-blue-100 rounded-lg px-3 py-2">
              {rca.summary}
            </p>
          )}
        </div>

        <button onClick={onAsk}
          className="px-3 py-2 rounded-lg border border-blue-200 text-blue-700 hover:bg-blue-50 text-sm font-semibold shrink-0">
          Ask AI
        </button>
      </div>

      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="border border-blue-100 rounded-xl p-4">
          <p className="text-xs text-gray-600">Root cause</p>
          <p className="text-sm font-medium text-gray-900 mt-1 whitespace-pre-wrap">
            {rca.root_cause || "No issues detected"}
          </p>
        </div>

        <div className="border border-blue-100 rounded-xl p-4">
          <p className="text-xs text-gray-600">Recommendations</p>
          {(rca.recommendations || []).length > 0 ? (
            <ul className="mt-1 space-y-1">
              {rca.recommendations.slice(0, 3).map((r, i) => (
                <li key={i} className="text-sm text-gray-900">
                  <span className={`inline-block w-2 h-2 rounded-full mr-2 ${
                    r.priority === "immediate" ? "bg-red-500" : r.priority === "short_term" ? "bg-yellow-500" : "bg-blue-500"
                  }`} />
                  {r.action}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm font-medium text-gray-900 mt-1">No recommendations</p>
          )}
        </div>
      </div>

      {/* Anomalies */}
      {(rca.anomalies || []).length > 0 && (
        <div className="mt-3">
          <p className="text-xs text-gray-500 mb-2">Detected Anomalies</p>
          <div className="flex gap-2 flex-wrap">
            {rca.anomalies.map((a, i) => (
              <span key={i} className={`px-2 py-1 rounded-lg text-xs font-medium border ${SEV_COLORS[a.severity] || SEV_COLORS.low}`}>
                {a.type}: {a.description?.slice(0, 60) || a.affected_model || "anomaly"}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="mt-4 pt-3 border-t border-blue-100 text-xs text-gray-500 flex flex-wrap gap-x-4 gap-y-1">
        <span>Traces: {rca.total_traces}</span>
        <span>Errors: {rca.total_errors}</span>
        <span>Cost: ${rca.total_cost_usd}</span>
        <span>{rca.timestamp ? new Date(rca.timestamp).toLocaleString() : "—"}</span>
      </div>
    </div>
  );
}


/* ---------- Chat Modal ---------- */

function ChatModal({ rca, onClose }) {
  const [messages, setMessages] = useState([
    {
      role: "ai",
      text: `Hi! I analyzed the LLM traces and found ${(rca.anomalies || []).length} anomalie(s). Health score: ${rca.health_score}/100. What would you like to understand?`,
    },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState(null);

  useEffect(() => {
    const el = document.getElementById("chat-box");
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const send = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMsg = input.trim();
    setMessages(prev => [...prev, { role: "user", text: userMsg }]);
    setInput("");
    setSending(true);

    try {
      const context = {
        rca_summary: rca.summary,
        root_cause: rca.root_cause,
        anomalies: JSON.stringify(rca.anomalies || []),
        recommendations: JSON.stringify(rca.recommendations || []),
        health_score: rca.health_score,
        total_traces: rca.total_traces,
        total_errors: rca.total_errors,
      };

      const res = await api.chat({
        message: userMsg,
        context,
        session_id: sessionId,
      });

      if (res?.session_id) setSessionId(res.session_id);

      setMessages(prev => [
        ...prev,
        { role: "ai", text: res?.response || "No response received." },
      ]);
    } catch (err) {
      console.error("Chat error:", err);
      setMessages(prev => [
        ...prev,
        { role: "ai", text: "Sorry — something went wrong. Please try again." },
      ]);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
      <div className="bg-white border border-blue-100 rounded-xl shadow-xl w-full max-w-lg flex flex-col max-h-[80vh]">
        <div className="p-4 border-b border-blue-100 flex justify-between items-center">
          <div>
            <h3 className="font-bold text-gray-900">AI Assistant</h3>
            <p className="text-xs text-gray-600 truncate max-w-[22rem]">
              Discussing: LLM Trace RCA (Health: {rca.health_score}/100)
            </p>
          </div>
          <button onClick={onClose}
            className="w-9 h-9 rounded-lg border border-blue-100 text-gray-600 hover:bg-blue-50"
            aria-label="Close">
            ×
          </button>
        </div>

        <div id="chat-box" className="flex-1 overflow-y-auto p-4 space-y-3 bg-white">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[80%] rounded-xl p-3 text-sm whitespace-pre-wrap border ${
                m.role === "user"
                  ? "bg-blue-600 text-white border-blue-600"
                  : "bg-white text-gray-900 border-blue-100"
              }`}>
                {m.text}
              </div>
            </div>
          ))}
          {sending && (
            <div className="flex justify-start">
              <div className="bg-blue-50 border border-blue-100 rounded-xl p-3 text-xs text-gray-600">
                Thinking…
              </div>
            </div>
          )}
        </div>

        <form onSubmit={send} className="p-4 border-t border-blue-100 bg-white">
          <div className="flex gap-2">
            <input value={input} onChange={e => setInput(e.target.value)}
              placeholder="Ask about the RCA..."
              className="flex-1 border border-blue-200 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={sending} autoFocus />
            <button type="submit" disabled={sending || !input.trim()}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-semibold">
              Send
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
