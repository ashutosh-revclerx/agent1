import { useState, useEffect, useMemo } from "react";
import { api } from "../services/api";
import { Spinner } from "./shared";
import { formatTime, formatDate } from "../utils/time";
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis,
  Tooltip, CartesianGrid, ResponsiveContainer,
} from "recharts";

const SEV_CFG = {
  critical: { pill: "bg-gray-900 text-white border-gray-900", pie: "#111827" },
  high:     { pill: "bg-gray-700 text-white border-gray-700", pie: "#374151" },
  medium:   { pill: "bg-gray-400 text-white border-gray-400", pie: "#6b7280" },
  low:      { pill: "bg-gray-200 text-gray-800 border-gray-200", pie: "#d1d5db" },
};

export default function Anomalies() {
  const [anomalies, setAnomalies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [severity, setSeverity] = useState("");

  useEffect(() => {
    fetchAnomalies(true);
    const interval = setInterval(() => fetchAnomalies(false), 10000);
    return () => clearInterval(interval);
  }, []);

  const fetchAnomalies = async (initial = false) => {
    try {
      if (initial) setLoading(true); else setRefreshing(true);
      const data = await api.getAnomalies();
      setAnomalies(data?.anomalies || []);
      setError(null);
    } catch (err) {
      setError(err?.message || "Failed to load anomalies");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const filtered = useMemo(() => {
    if (!severity) return anomalies;
    return anomalies.filter((a) => (a?.severity || "medium").toLowerCase() === severity);
  }, [anomalies, severity]);

  const counts = useMemo(() => {
    const c = { critical: 0, high: 0, medium: 0, low: 0, total: anomalies.length };
    for (const a of anomalies) {
      const s = (a?.severity || "medium").toLowerCase();
      if (c[s] !== undefined) c[s] += 1; else c.medium += 1;
    }
    return c;
  }, [anomalies]);

  const pieData = [
    { name: "Critical", value: counts.critical, color: SEV_CFG.critical.pie },
    { name: "High",     value: counts.high,     color: SEV_CFG.high.pie },
    { name: "Medium",   value: counts.medium,   color: SEV_CFG.medium.pie },
    { name: "Low",      value: counts.low,      color: SEV_CFG.low.pie },
  ].filter((d) => d.value > 0);

  const topMetrics = useMemo(() => {
    const map = {};
    for (const a of anomalies) {
      const m = a?.metric || "Unknown";
      map[m] = (map[m] || 0) + 1;
    }
    return Object.entries(map)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([name, count]) => ({
        name: name.length > 20 ? name.slice(0, 18) + "…" : name,
        count,
      }));
  }, [anomalies]);

  if (loading) return <Spinner />;

  if (error) {
    return (
      <div className="bg-white border border-gray-200 rounded-xl p-6">
        <p className="font-semibold text-gray-900 mb-2">Failed to load anomalies</p>
        <p className="text-sm text-gray-600 mb-4">{error}</p>
        <button onClick={() => fetchAnomalies(true)} className="px-4 py-2 bg-gray-900 text-white rounded-lg hover:bg-black text-sm font-semibold">Retry</button>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Hero */}
      <div className="bg-gray-900 rounded-2xl p-6 text-white">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className={`w-2 h-2 rounded-full ${refreshing ? "bg-yellow-400 animate-pulse" : "bg-green-400 animate-pulse"}`} />
              <span className="text-gray-400 text-xs font-semibold uppercase tracking-widest">Auto-refresh · 10s</span>
            </div>
            <h1 className="text-2xl font-bold">Anomaly Detection</h1>
            <p className="text-gray-400 text-sm mt-1">AI-detected infrastructure deviations</p>
          </div>
          <div className="flex gap-3 flex-wrap items-center">
            <KpiBox label="Total" value={counts.total} />
            <KpiBox label="Critical" value={counts.critical} />
            <KpiBox label="High" value={counts.high} />
            <button
              onClick={() => fetchAnomalies(false)}
              disabled={refreshing}
              className="bg-white text-gray-900 px-4 py-2.5 rounded-xl text-sm font-bold hover:bg-gray-100 shadow disabled:opacity-60"
            >
              {refreshing ? "↻ Refreshing…" : "↻ Refresh"}
            </button>
          </div>
        </div>
      </div>

      {/* Severity cards (filter) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { key: "critical", label: "Critical", icon: "⬛" },
          { key: "high",     label: "High",     icon: "◼️" },
          { key: "medium",   label: "Medium",   icon: "◻️" },
          { key: "low",      label: "Low",      icon: "⬜" },
        ].map(({ key, label, icon }) => (
          <button
            key={key}
            onClick={() => setSeverity(severity === key ? "" : key)}
            className={`bg-white rounded-2xl p-4 border-2 text-left hover:shadow-md transition-all ${severity === key ? "border-gray-900 shadow-md" : "border-gray-200"}`}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-xl">{icon}</span>
              <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${severity === key ? "bg-black text-white" : "bg-gray-100 text-gray-600"}`}>
                {severity === key ? "ACTIVE" : "FILTER"}
              </span>
            </div>
            <p className="text-sm text-gray-500">{label}</p>
            <p className="text-3xl font-extrabold text-gray-900 mt-0.5">{counts[key]}</p>
            <div className="mt-2 h-1.5 bg-gray-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-gray-900 rounded-full"
                style={{ width: counts.total > 0 ? `${Math.round((counts[key] / counts.total) * 100)}%` : "0%" }}
              />
            </div>
            <p className="text-xs text-gray-400 mt-1">
              {counts.total > 0 ? Math.round((counts[key] / counts.total) * 100) : 0}% of total
            </p>
          </button>
        ))}
      </div>

      {/* Charts */}
      {anomalies.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
          {topMetrics.length > 0 && (
            <div className="lg:col-span-3 bg-white border border-gray-200 rounded-2xl p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="font-bold text-gray-900">Top Anomalous Metrics</h3>
                  <p className="text-xs text-gray-500 mt-0.5">Most triggered metric names (from DB)</p>
                </div>
                <span className="text-xs font-bold bg-black text-white px-2.5 py-1 rounded-full">DB</span>
              </div>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={topMetrics} layout="vertical" barSize={14}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 10, fill: "#6b7280" }} axisLine={false} tickLine={false} width={120} />
                  <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid #e5e7eb", fontSize: 12 }} labelStyle={{ color: "#111827", fontWeight: 700 }} />
                  <Bar dataKey="count" fill="#111827" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
          <div className={`${topMetrics.length > 0 ? "lg:col-span-2" : "lg:col-span-5"} bg-white border border-gray-200 rounded-2xl p-5`}>
            <div className="mb-3">
              <h3 className="font-bold text-gray-900">Severity Distribution</h3>
              <p className="text-xs text-gray-500 mt-0.5">Breakdown from DB records</p>
            </div>
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={75} paddingAngle={3} dataKey="value">
                  {pieData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                </Pie>
                <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid #e5e7eb", fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
            <div className="space-y-1.5 mt-1">
              {pieData.map((d) => (
                <div key={d.name} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-sm" style={{ background: d.color }} />
                    <span className="text-xs text-gray-600">{d.name}</span>
                  </div>
                  <span className="text-xs font-bold text-gray-900">{d.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Result strip */}
      <div className="bg-white border border-gray-200 rounded-2xl p-4 flex items-center justify-between gap-4 flex-wrap">
        <p className="text-sm text-gray-600">
          Showing <span className="font-extrabold text-gray-900">{filtered.length}</span> of <span className="font-bold text-gray-900">{anomalies.length}</span> anomalies
          {severity && <> · filtered by <span className="font-bold capitalize">{severity}</span></>}
        </p>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
          <span className="text-xs text-gray-500">Live · auto-refresh 10s</span>
        </div>
      </div>

      {/* Anomaly cards */}
      {filtered.length === 0 ? (
        <div className="bg-white border border-gray-200 rounded-2xl p-12 text-center">
          <p className="text-4xl mb-3">🎉</p>
          <p className="text-gray-900 font-bold text-lg">{severity ? "No anomalies match this filter." : "No anomalies detected."}</p>
          <p className="text-sm text-gray-500 mt-1">{severity ? "Try a different severity filter." : "Everything looks stable."}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((a, idx) => <AnomalyCard key={a?._id || idx} anomaly={a} />)}
        </div>
      )}

      {anomalies.length > 0 && (
        <p className="text-center text-xs text-gray-400 pb-2">
          ↻ Auto-refreshing every 10 seconds · {filtered.length} of {anomalies.length} shown
        </p>
      )}
    </div>
  );
}

function AnomalyCard({ anomaly }) {
  const sev = (anomaly?.severity || "medium").toLowerCase();
  const cfg = SEV_CFG[sev] || SEV_CFG.medium;
  const metric = anomaly?.metric || "Unknown Metric";
  const instance = anomaly?.instance;
  const symptom = anomaly?.symptom || anomaly?.reason || "Anomalous behavior detected";
  const observed = anomaly?.observed !== undefined ? anomaly.observed : anomaly?.value !== undefined ? anomaly.value : null;
  const observedText = typeof observed === "number" ? observed.toFixed(2) : observed !== null ? String(observed) : "N/A";
  const expectedText = anomaly?.expected || "Normal baseline";
  const ts = anomaly?.timestamp ? new Date(anomaly.timestamp) : null;
  const timeText = ts ? formatTime(ts) : "—";
  const dateText = ts ? formatDate(ts) : "";

  const handleViewGrafana = async () => {
    if (!instance) { alert("No instance information available"); return; }
    try {
      const { grafana_url } = await api.getGrafanaUrl(instance);
      window.open(grafana_url, "_blank");
    } catch { alert("Failed to open Grafana."); }
  };

  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-5 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`px-2.5 py-1 rounded-full text-xs font-extrabold border ${cfg.pill}`}>{sev.toUpperCase()}</span>
            <h3 className="font-bold text-gray-900 truncate">{metric}</h3>
          </div>
          {instance && (
            <p className="text-xs text-gray-500 mt-2">
              <span className="font-bold text-gray-700">Instance:</span>{" "}
              <span className="font-mono break-all">{instance}</span>
            </p>
          )}
          <div className="mt-3 bg-gray-50 border border-gray-200 rounded-xl px-4 py-2.5">
            <p className="text-xs font-bold text-gray-600 mb-0.5 uppercase tracking-wider">Symptom</p>
            <p className="text-sm text-gray-800">{symptom}</p>
          </div>
        </div>
        <div className="text-right flex-shrink-0">
          <p className="text-xs text-gray-400 uppercase tracking-wider">Detected</p>
          <p className="text-sm font-bold text-gray-900 mt-1">{timeText}</p>
          {dateText && <p className="text-xs text-gray-400">{dateText}</p>}
          {instance && (
            <button
              onClick={handleViewGrafana}
              className="mt-2 px-3 py-1.5 bg-gray-900 text-white text-xs font-bold rounded-lg hover:bg-black transition-colors"
            >
              📊 Grafana
            </button>
          )}
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="border-2 border-gray-100 rounded-xl p-4 bg-gray-50">
          <p className="text-xs font-bold text-gray-500 uppercase tracking-wider">Observed</p>
          <p className="text-2xl font-extrabold text-gray-900 mt-1">{observedText}</p>
        </div>
        <div className="border-2 border-gray-100 rounded-xl p-4">
          <p className="text-xs font-bold text-gray-500 uppercase tracking-wider">Expected</p>
          <p className="text-sm font-semibold text-gray-800 mt-1">{expectedText}</p>
        </div>
      </div>
      <div className="mt-3 pt-3 border-t border-gray-100 flex flex-wrap gap-x-4 gap-y-1">
        {anomaly?._id && <span className="text-xs text-gray-400 font-mono">ID: {String(anomaly._id).slice(0, 8)}…</span>}
        {anomaly?.batch_id && <span className="text-xs text-gray-400 font-mono">Batch: {String(anomaly.batch_id).slice(0, 8)}…</span>}
        {anomaly?.incident_id && <span className="text-xs text-gray-400 font-mono">Incident: {String(anomaly.incident_id).slice(0, 8)}…</span>}
      </div>
    </div>
  );
}

function KpiBox({ label, value }) {
  return (
    <div className="bg-white/10 border border-white/20 rounded-xl px-3 py-2 text-center">
      <p className="text-gray-400 text-xs uppercase tracking-wide">{label}</p>
      <p className="text-white font-extrabold text-lg mt-0.5">{value}</p>
    </div>
  );
}

