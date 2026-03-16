import { useState, useEffect, useMemo } from "react";
import { api } from "../services/api";
import { Spinner } from "./shared";
import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
  AreaChart, Area,
} from "recharts";

const SEV_COLORS = {
  critical: "bg-gray-900 text-white border-gray-900",
  high:     "bg-gray-700 text-white border-gray-700",
  medium:   "bg-gray-400 text-white border-gray-400",
  low:      "bg-gray-200 text-gray-800 border-gray-200",
};

const MODEL_PALETTE = ["#111827", "#374151", "#6b7280", "#9ca3af", "#d1d5db", "#4b5563", "#1f2937"];

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
  const [chatOpen, setChatOpen] = useState(false);
  const [activeRca, setActiveRca] = useState(null);

  useEffect(() => { fetchWatchedUsers(); }, []);

  useEffect(() => {
    fetchData(true);
    let interval;
    if (isAutoRefresh) {
      interval = setInterval(() => fetchData(false), 30000);
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
    } catch {
      alert("Failed to remove user");
    }
  };

  const runRcaAnalysis = async () => {
    setRunningRca(true);
    try {
      const res = await api.runLangfuseRCA(Math.min(hours, 24), selectedUser || null);
      if (res.rca) setRcaResults((prev) => [res.rca, ...prev]);
      else alert(res.message || "No traces to analyze");
    } catch (err) {
      alert(err.message || "RCA analysis failed");
    } finally {
      setRunningRca(false);
    }
  };

  const modelPieData = useMemo(() => {
    if (!stats?.models_used) return [];
    return Object.entries(stats.models_used).map(([model, count], i) => ({
      name: model,
      value: count,
      color: MODEL_PALETTE[i % MODEL_PALETTE.length],
    }));
  }, [stats]);

  const tokenTrend = useMemo(() => {
    if (!traces.length) return [];
    return traces.slice(0, 10).reverse().map((t, i) => ({
      i: i + 1,
      tokens: t.total_tokens || 0,
      cost: parseFloat(t.cost_usd || 0),
    }));
  }, [traces]);

  const latencyBuckets = useMemo(() => {
    if (!traces.length) return [];
    const buckets = { "<1s": 0, "1-3s": 0, "3-5s": 0, ">5s": 0 };
    for (const t of traces) {
      const l = t.latency_s || 0;
      if (l < 1) buckets["<1s"]++;
      else if (l < 3) buckets["1-3s"]++;
      else if (l < 5) buckets["3-5s"]++;
      else buckets[">5s"]++;
    }
    return Object.entries(buckets).map(([range, count]) => ({ range, count }));
  }, [traces]);

  const statCards = stats ? [
    { label: "Total Traces",   value: stats.total_traces,                              icon: "📡" },
    { label: "Total Tokens",   value: (stats.total_tokens || 0).toLocaleString(),       icon: "🔤" },
    { label: "Total Cost",     value: `$${stats.total_cost_usd}`,                       icon: "💰" },
    { label: "Avg Latency",    value: `${stats.avg_latency_s}s`,                        icon: "⏱️" },
    { label: "Input Tokens",   value: (stats.total_input_tokens || 0).toLocaleString(), icon: "📥" },
    { label: "Output Tokens",  value: (stats.total_output_tokens || 0).toLocaleString(), icon: "📤" },
    { label: "Errors",         value: stats.error_count,                                icon: "⚠️" },
    { label: "Active Users",   value: Object.keys(stats.active_users || {}).length,     icon: "👥" },
  ] : [];

  return (
    <div className="space-y-5">
      {/* Hero */}
      <div className="bg-gray-900 rounded-2xl p-6 text-white">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
              <span className="text-gray-400 text-xs font-semibold uppercase tracking-widest">
                {isAutoRefresh ? "Auto-refresh · 30s" : "Manual refresh"}
              </span>
            </div>
            <h1 className="text-2xl font-bold">🤖 LLM Monitor</h1>
            <p className="text-gray-400 text-sm mt-1">Langfuse trace ingestion &amp; analytics</p>
          </div>
          <div className="flex gap-2 flex-wrap items-center">
            <select
              value={selectedUser}
              onChange={(e) => setSelectedUser(e.target.value)}
              className="bg-white/15 border border-white/30 text-white rounded-xl px-3 py-2 text-sm focus:ring-2 focus:ring-white/50 focus:outline-none"
            >
              <option value="" className="text-gray-800">All Users</option>
              {watchedUsers.map((u) => (
                <option key={u.langfuse_user_id} value={u.langfuse_user_id} className="text-gray-800">
                  {u.label}
                </option>
              ))}
            </select>
            <select
              value={hours}
              onChange={(e) => setHours(Number(e.target.value))}
              className="bg-white/15 border border-white/30 text-white rounded-xl px-3 py-2 text-sm focus:ring-2 focus:ring-white/50 focus:outline-none"
            >
              <option value={1}   className="text-gray-800">Last 1h</option>
              <option value={6}   className="text-gray-800">Last 6h</option>
              <option value={24}  className="text-gray-800">Last 24h</option>
              <option value={72}  className="text-gray-800">Last 3d</option>
              <option value={168} className="text-gray-800">Last 7d</option>
            </select>
            <label className="flex items-center gap-2 text-sm text-white bg-white/15 border border-white/30 rounded-xl px-3 py-2 cursor-pointer hover:bg-white/20">
              <input
                type="checkbox"
                checked={isAutoRefresh}
                onChange={(e) => setIsAutoRefresh(e.target.checked)}
                className="rounded"
              />
              Auto-refresh
            </label>
            <button
              onClick={() => fetchData(true)}
              className="bg-white text-gray-900 px-4 py-2.5 rounded-xl text-sm font-bold hover:bg-gray-100 shadow transition-colors"
            >
              ↻ Refresh
            </button>
          </div>
        </div>
      </div>

      {/* Watched Users */}
      <div className="bg-white rounded-2xl border border-gray-200 p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-bold text-gray-900">Watched Langfuse Users</h2>
          <span className="text-xs font-bold bg-black text-white px-2.5 py-1 rounded-full">
            {watchedUsers.length} watching
          </span>
        </div>
        <div className="flex gap-2 flex-wrap mb-4 min-h-8">
          {watchedUsers.length === 0 && (
            <span className="text-gray-400 text-sm self-center">No users being watched yet</span>
          )}
          {watchedUsers.map((u) => (
            <div
              key={u.langfuse_user_id}
              className="flex items-center gap-2 bg-gray-100 border border-gray-200 rounded-full px-3 py-1.5 hover:bg-gray-200 transition-colors"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              <span className="text-sm text-gray-800 font-semibold">{u.label}</span>
              {u.label !== u.langfuse_user_id && (
                <span className="text-xs text-gray-500">({u.langfuse_user_id})</span>
              )}
              <button
                onClick={() => removeWatchedUser(u.langfuse_user_id)}
                className="text-red-400 hover:text-red-600 text-xs font-bold ml-0.5 w-4 h-4 flex items-center justify-center rounded-full hover:bg-red-50"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
        <div className="flex gap-2 flex-wrap border-t border-gray-100 pt-4">
          <input
            type="text"
            value={newUserId}
            onChange={(e) => setNewUserId(e.target.value)}
            placeholder="Langfuse userId (e.g. contract management agent)"
            className="bg-gray-50 border border-gray-200 rounded-xl px-3 py-2 text-sm flex-1 min-w-48 focus:ring-2 focus:ring-gray-900 focus:border-gray-900 focus:outline-none"
          />
          <input
            type="text"
            value={newUserLabel}
            onChange={(e) => setNewUserLabel(e.target.value)}
            placeholder="Label (optional)"
            className="bg-gray-50 border border-gray-200 rounded-xl px-3 py-2 text-sm w-36 focus:ring-2 focus:ring-gray-900 focus:border-gray-900 focus:outline-none"
          />
          <button
            onClick={addWatchedUser}
            disabled={adding || !newUserId.trim()}
            className="bg-gray-900 hover:bg-black disabled:opacity-50 text-white px-4 py-2 rounded-xl text-sm font-bold transition-colors"
          >
            {adding ? "Adding…" : "+ Watch"}
          </button>
        </div>
      </div>

      {loading ? (
        <Spinner />
      ) : (
        <>
          {/* Stat Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {statCards.map(({ label, value, icon }) => (
              <div key={label} className="bg-white rounded-2xl border border-gray-200 p-4 hover:shadow-md transition-shadow">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-2xl">{icon}</span>
                  <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                </div>
                <p className="text-gray-500 text-xs">{label}</p>
                <p className="text-gray-900 text-2xl font-extrabold mt-0.5">{value}</p>
              </div>
            ))}
          </div>

          {/* Charts Row */}
          {(tokenTrend.length > 0 || modelPieData.length > 0) && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* Token Trend */}
              {tokenTrend.length > 1 && (
                <div className="lg:col-span-2 bg-white border border-gray-200 rounded-2xl p-5">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h3 className="font-bold text-gray-900">Token Usage — Recent Traces</h3>
                      <p className="text-xs text-gray-500 mt-0.5">Tokens consumed per trace (last 10)</p>
                    </div>
                    <span className="text-xs font-bold bg-black text-white px-2.5 py-1 rounded-full">
                      {(stats?.total_tokens || 0).toLocaleString()} total
                    </span>
                  </div>
                  <ResponsiveContainer width="100%" height={190}>
                    <AreaChart data={tokenTrend}>
                      <defs>
                        <linearGradient id="tokenGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%"  stopColor="#111827" stopOpacity={0.15} />
                          <stop offset="95%" stopColor="#111827" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                      <XAxis dataKey="i" tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} label={{ value: "Trace", position: "insideBottom", offset: -2, fontSize: 10, fill: "#9ca3af" }} />
                      <YAxis tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
                      <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid #e5e7eb", fontSize: 12 }} labelStyle={{ color: "#111827", fontWeight: 700 }} />
                      <Area type="monotone" dataKey="tokens" stroke="#111827" strokeWidth={2.5} fill="url(#tokenGrad)" dot={{ fill: "#111827", r: 3.5, strokeWidth: 2, stroke: "#fff" }} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Model Distribution Pie */}
              {modelPieData.length > 0 && (
                <div className="bg-white border border-gray-200 rounded-2xl p-5">
                  <div className="mb-3">
                    <h3 className="font-bold text-gray-900">Model Distribution</h3>
                    <p className="text-xs text-gray-500 mt-0.5">Call count by model</p>
                  </div>
                  <ResponsiveContainer width="100%" height={160}>
                    <PieChart>
                      <Pie data={modelPieData} cx="50%" cy="50%" innerRadius={44} outerRadius={68} paddingAngle={3} dataKey="value">
                        {modelPieData.map((entry, i) => (
                          <Cell key={i} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid #e5e7eb", fontSize: 12 }} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="space-y-1 mt-1">
                    {modelPieData.map((d, i) => (
                      <div key={i} className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5">
                          <span className="w-2.5 h-2.5 rounded-sm" style={{ background: d.color }} />
                          <span className="text-xs text-gray-600 truncate max-w-[120px]">{d.name}</span>
                        </div>
                        <span className="text-xs font-bold text-gray-700">{d.value} calls</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Latency Distribution — always rendered once below charts row */}
          {latencyBuckets.length > 0 && (
            <LatencyChart buckets={latencyBuckets} avgLatency={stats?.avg_latency_s} />
          )}

          {/* RCA Section */}
          <div className="bg-white rounded-2xl border border-gray-200 p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="font-bold text-gray-900">🔍 RCA Analysis</h2>
                <p className="text-xs text-gray-500 mt-0.5">LLM-powered root cause analysis of trace anomalies</p>
              </div>
              <div className="flex items-center gap-3">
                {rcaResults.length > 0 && (
                  <span className="text-xs font-bold bg-black text-white px-2.5 py-1 rounded-full">
                    {rcaResults.length} reports
                  </span>
                )}
                <button
                  onClick={runRcaAnalysis}
                  disabled={runningRca}
                  className="bg-gray-900 hover:bg-black disabled:opacity-50 text-white px-4 py-2 rounded-xl text-sm font-bold transition-colors"
                >
                  {runningRca ? "⟳ Analyzing…" : "▶ Run Analysis"}
                </button>
              </div>
            </div>

            {rcaResults.length === 0 ? (
              <div className="text-center py-8 border-2 border-dashed border-gray-200 rounded-xl">
                <p className="text-3xl mb-2">🔬</p>
                <p className="text-gray-500 text-sm">
                  No RCA results yet. Click <strong>Run Analysis</strong> or wait for the next poll cycle.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {rcaResults.map((rca, idx) => (
                  <RcaCard
                    key={rca.timestamp || idx}
                    rca={rca}
                    onAsk={() => { setActiveRca(rca); setChatOpen(true); }}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Traces Table */}
          <div className="bg-white rounded-2xl border border-gray-200">
            <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
              <div>
                <h2 className="font-bold text-gray-900">
                  Recent Traces <span className="text-gray-900 font-extrabold">({traces.length})</span>
                </h2>
                <p className="text-xs text-gray-500 mt-0.5">Latest LLM trace ingestion events</p>
              </div>
              <div className="flex items-center gap-2">
                {stats?.error_count > 0 && (
                  <span className="text-xs font-bold bg-red-50 text-red-700 border border-red-200 px-2.5 py-1 rounded-full">
                    {stats.error_count} errors
                  </span>
                )}
                <span className="text-xs font-bold bg-black text-white px-2.5 py-1 rounded-full">
                  ${stats?.total_cost_usd || "0.00"} total
                </span>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-gray-700">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50 text-left">
                    <th className="py-3 px-4 font-bold text-gray-600 text-xs uppercase tracking-wider">Name</th>
                    <th className="py-3 px-4 font-bold text-gray-600 text-xs uppercase tracking-wider">User</th>
                    <th className="py-3 px-4 font-bold text-gray-600 text-xs uppercase tracking-wider">Model</th>
                    <th className="py-3 px-4 font-bold text-gray-600 text-xs uppercase tracking-wider text-right">Tokens</th>
                    <th className="py-3 px-4 font-bold text-gray-600 text-xs uppercase tracking-wider text-right">Cost</th>
                    <th className="py-3 px-4 font-bold text-gray-600 text-xs uppercase tracking-wider text-right">Latency</th>
                    <th className="py-3 px-4 font-bold text-gray-600 text-xs uppercase tracking-wider">Status</th>
                    <th className="py-3 px-4 font-bold text-gray-600 text-xs uppercase tracking-wider">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {traces.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="py-12 text-center text-gray-400">
                        <p className="text-3xl mb-2">📡</p>
                        <p>No traces yet. Add a watched user above and wait up to 2 minutes.</p>
                      </td>
                    </tr>
                  ) : (
                    traces.map((trace) => (
                      <tr
                        key={trace.trace_id}
                        className="border-b border-gray-50 hover:bg-gray-50/50 transition-colors"
                      >
                        <td className="py-3 px-4 text-gray-900 text-xs font-mono truncate max-w-32">
                          {trace.name || "—"}
                        </td>
                        <td className="py-3 px-4 text-xs truncate max-w-28 text-gray-700">
                          {trace.langfuse_user_id}
                        </td>
                        <td className="py-3 px-4">
                          <span className="text-xs font-bold text-gray-700 bg-gray-100 border border-gray-200 px-2 py-0.5 rounded-full">
                            {trace.model || "—"}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-xs">
                          {(trace.total_tokens || 0).toLocaleString()}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <span className="text-xs font-bold text-gray-700">${trace.cost_usd}</span>
                        </td>
                        <td className="py-3 px-4 text-right">
                          <span className={`text-xs font-semibold ${
                            (trace.latency_s || 0) > 5 ? "text-red-600" :
                            (trace.latency_s || 0) > 3 ? "text-yellow-600" : "text-gray-700"
                          }`}>
                            {trace.latency_s ? `${trace.latency_s}s` : "—"}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                            trace.status === "error"
                              ? "bg-red-100 text-red-700 border border-red-200"
                              : "bg-green-100 text-green-700 border border-green-200"
                          }`}>
                            {trace.status}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-xs text-gray-400 whitespace-nowrap">
                          {new Date(trace.timestamp).toLocaleString()}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {chatOpen && activeRca && (
        <ChatModal rca={activeRca} onClose={() => setChatOpen(false)} />
      )}
    </div>
  );
}

function RcaCard({ rca, onAsk }) {
  const anomalyCount = (rca.anomalies || []).length;
  const healthScore  = rca.health_score ?? 100;
  const healthColor  =
    healthScore >= 80 ? "text-green-600" :
    healthScore >= 50 ? "text-yellow-600" : "text-red-600";
  const healthBg     =
    healthScore >= 80 ? "bg-green-50 border-green-200" :
    healthScore >= 50 ? "bg-yellow-50 border-yellow-200" : "bg-red-50 border-red-200";

  return (
    <div className="border border-gray-200 rounded-2xl p-5 hover:shadow-md transition-shadow bg-white">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="px-2.5 py-1 rounded-full text-xs font-extrabold bg-black text-white">RCA</span>
            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border ${healthBg}`}>
              <span className={`text-sm font-extrabold ${healthColor}`}>{healthScore}/100</span>
              <span className="text-xs text-gray-500">health</span>
            </div>
            {anomalyCount > 0 && (
              <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-red-100 text-red-700 border border-red-200">
                {anomalyCount} anomal{anomalyCount === 1 ? "y" : "ies"}
              </span>
            )}
          </div>

          <div className="mt-3 h-2 bg-gray-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-700 ${
                healthScore >= 80 ? "bg-green-500" :
                healthScore >= 50 ? "bg-yellow-500" : "bg-red-500"
              }`}
              style={{ width: `${healthScore}%` }}
            />
          </div>

          {rca.summary && (
            <div className="mt-3 bg-gray-50 border border-gray-200 rounded-xl px-4 py-2.5">
              <p className="text-xs font-bold text-gray-600 uppercase tracking-wider mb-0.5">Summary</p>
              <p className="text-sm text-gray-800">{rca.summary}</p>
            </div>
          )}
        </div>
        <button
          onClick={onAsk}
          className="px-3 py-2 rounded-xl bg-gray-900 text-white hover:bg-black text-xs font-bold flex-shrink-0 transition-colors"
        >
          Ask AI
        </button>
      </div>

      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="border border-gray-200 rounded-xl p-4 bg-gray-50/50">
          <p className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-1.5">Root Cause</p>
          <p className="text-sm text-gray-900 whitespace-pre-wrap">{rca.root_cause || "No issues detected"}</p>
        </div>
        <div className="border border-gray-200 rounded-xl p-4">
          <p className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-1.5">Recommendations</p>
          {(rca.recommendations || []).length > 0 ? (
            <ul className="space-y-1.5">
              {rca.recommendations.slice(0, 3).map((r, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-900">
                  <span className={`w-2 h-2 rounded-full flex-shrink-0 mt-1.5 ${
                    r.priority === "immediate" ? "bg-red-500" :
                    r.priority === "short_term" ? "bg-yellow-500" : "bg-gray-400"
                  }`} />
                  {r.action}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-600">No recommendations</p>
          )}
        </div>
      </div>

      {(rca.anomalies || []).length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Detected Anomalies</p>
          <div className="flex gap-2 flex-wrap">
            {rca.anomalies.map((a, i) => (
              <span key={i} className={`px-2 py-1 rounded-lg text-xs font-semibold border ${SEV_COLORS[a.severity] || SEV_COLORS.low}`}>
                {a.type}: {a.description?.slice(0, 55) || a.affected_model || "anomaly"}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="mt-3 pt-3 border-t border-gray-100 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400">
        <span>Traces: <strong className="text-gray-600">{rca.total_traces}</strong></span>
        <span>Errors: <strong className="text-gray-600">{rca.total_errors}</strong></span>
        <span>Cost: <strong className="text-gray-600">${rca.total_cost_usd}</strong></span>
        <span>{rca.timestamp ? new Date(rca.timestamp).toLocaleString() : "—"}</span>
      </div>
    </div>
  );
}

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
    const el = document.getElementById("lf-chat-box");
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const send = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;
    const userMsg = input.trim();
    setMessages((prev) => [...prev, { role: "user", text: userMsg }]);
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
      const res = await api.chat({ message: userMsg, context, session_id: sessionId });
      if (res?.session_id) setSessionId(res.session_id);
      setMessages((prev) => [...prev, { role: "ai", text: res?.response || "No response received." }]);
    } catch {
      setMessages((prev) => [...prev, { role: "ai", text: "Sorry — something went wrong. Please try again." }]);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-white border border-gray-200 rounded-2xl shadow-2xl w-full max-w-lg flex flex-col max-h-[80vh]">
        <div className="p-4 border-b border-gray-200 flex items-center justify-between bg-gray-900 rounded-t-2xl">
          <div>
            <h3 className="font-bold text-white">AI Assistant</h3>
            <p className="text-xs text-gray-400">Discussing LLM Trace RCA · Health: {rca.health_score}/100</p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg bg-white/20 text-white hover:bg-white/30 font-bold text-lg flex items-center justify-center"
          >
            ×
          </button>
        </div>
        <div id="lf-chat-box" className="flex-1 overflow-y-auto p-4 space-y-3 bg-white">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[80%] rounded-2xl p-3 text-sm whitespace-pre-wrap ${
                m.role === "user"
                  ? "bg-gray-900 text-white"
                  : "bg-gray-100 text-gray-900 border border-gray-200"
              }`}>
                {m.text}
              </div>
            </div>
          ))}
          {sending && (
            <div className="flex justify-start">
              <div className="bg-gray-100 border border-gray-200 rounded-2xl p-3 text-xs text-gray-500 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce" />
                <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce [animation-delay:0.1s]" />
                <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce [animation-delay:0.2s]" />
              </div>
            </div>
          )}
        </div>
        <form onSubmit={send} className="p-4 border-t border-gray-200 bg-white rounded-b-2xl">
          <div className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about the RCA…"
              className="flex-1 border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900"
              disabled={sending}
              autoFocus
            />
            <button
              type="submit"
              disabled={sending || !input.trim()}
              className="bg-gray-900 text-white px-4 py-2.5 rounded-xl hover:bg-black disabled:opacity-50 font-bold text-sm transition-colors"
            >
              Send
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function LatencyChart({ buckets, avgLatency }) {
  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="font-bold text-gray-900">Latency Distribution</h3>
          <p className="text-xs text-gray-500 mt-0.5">Response time buckets across all traces</p>
        </div>
        {avgLatency != null && (
          <span className="text-xs font-bold bg-gray-100 text-gray-700 border border-gray-200 px-2.5 py-1 rounded-full">
            Avg: {avgLatency}s
          </span>
        )}
      </div>
      <ResponsiveContainer width="100%" height={170}>
        <BarChart data={buckets} barSize={44}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis dataKey="range" tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
          <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid #e5e7eb", fontSize: 12 }} />
          <Bar dataKey="count" fill="#374151" radius={[5, 5, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
