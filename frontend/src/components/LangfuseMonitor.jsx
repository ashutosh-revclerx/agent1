import { useState, useEffect } from "react";
import { api } from "../services/api";

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
      const res = await api.getLangfuseWatchedUsers();
      setWatchedUsers(res.users || []);
    } catch (err) {
      console.error("Failed to fetch watched users", err);
    }
  };

  const fetchData = async () => {
    setLoading(true);
    try {
      const [statsRes, tracesRes] = await Promise.all([
        api.getLangfuseStats(hours, selectedUser || null),
        api.getLangfuseTraces(hours, selectedUser || null, 50),
      ]);
      setStats(statsRes);
      setTraces(tracesRes.traces || []);
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
      await api.addLangfuseWatchedUser(newUserId.trim(), newUserLabel.trim() || newUserId.trim());
      setNewUserId("");
      setNewUserLabel("");
      await fetchWatchedUsers();
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
          <button onClick={fetchData}
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
        <div className="text-gray-400 py-8 text-center">Loading LLM metrics...</div>
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
    </div>
  );
}
