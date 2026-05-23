import { useState, useEffect, useRef } from "react";
import { api } from "../services/api";
import { Spinner } from "./shared";
import {
  AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
} from "recharts";

const MAX_HISTORY = 20;

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);
  const tickRef = useRef(0);

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchStats = async () => {
    try {
      const [statsData, healthData] = await Promise.all([
        api.getStats(),
        api.getHealth(),
      ]);
      setStats(statsData);
      setHealth(healthData);
      setError(null);
      tickRef.current += 1;
      const now = new Date();
      const label = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`;
      setHistory((prev) => {
        const next = [...prev, {
          time: label,
          metrics: statsData?.collections?.metrics_batches?.total ?? 0,
          anomalies: statsData?.collections?.anomalies?.total ?? 0,
          open: statsData?.collections?.anomalies?.open ?? 0,
          rca: statsData?.collections?.anomalies?.analyzed ?? 0,
        }];
        return next.length > MAX_HISTORY ? next.slice(-MAX_HISTORY) : next;
      });
    } catch (err) {
      setError(err?.message || "Failed to connect");
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <Spinner />;
  }

  if (error) {
    return (
      <div className="bg-white border border-gray-200 rounded-xl p-6">
        <p className="text-gray-900 font-semibold mb-2">Connection error</p>
        <p className="text-sm text-gray-600 mb-4">{error}</p>
        <button onClick={fetchStats} className="px-4 py-2 bg-gray-900 text-white rounded-lg hover:bg-black text-sm font-semibold">Retry</button>
      </div>
    );
  }

  const metricsTotal = stats?.collections?.metrics_batches?.total ?? 0;
  const anomaliesTotal = stats?.collections?.anomalies?.total ?? 0;
  const openIssues = stats?.collections?.anomalies?.open ?? 0;
  const rcaDone = stats?.collections?.anomalies?.analyzed ?? 0;
  const emailEnabled = !!stats?.notifications?.email?.enabled;
  const slackEnabled = !!stats?.notifications?.slack?.enabled && !!stats?.notifications?.slack?.configured;
  const systemOnline = health?.status === "running";
  const resolvedPct = anomaliesTotal > 0 ? Math.round((rcaDone / anomaliesTotal) * 100) : 0;

  const kpiBar = [
    { name: "Metric Batches", value: metricsTotal },
    { name: "Anomalies", value: anomaliesTotal },
    { name: "Open Issues", value: openIssues },
    { name: "RCA Done", value: rcaDone },
  ];

  const compHealth = [
    { label: "API Server",  ok: true },
    { label: "MongoDB",     ok: !!stats?.collections },
    { label: "Prometheus",  ok: !!health?.prometheus },
    { label: "LLM Service", ok: !!health?.llm },
  ];

  return (
    <div className="space-y-6">
      {/* Hero Section - Sleek Black */}
      <div className="bg-zinc-950 rounded-[2rem] p-8 text-white shadow-2xl border border-zinc-800 relative overflow-hidden">
        {/* Decorative background element */}
        <div className="absolute top-0 right-0 w-64 h-64 bg-white opacity-[0.03] rounded-full -mr-32 -mt-32 blur-3xl" />
        
        <div className="flex items-start justify-between gap-6 relative z-10 flex-wrap">
          <div>
            <div className="flex items-center gap-2 mb-3">
              <span className={`w-2 h-2 rounded-full ${systemOnline ? "bg-white shadow-[0_0_8px_rgba(255,255,255,0.8)] animate-pulse" : "bg-zinc-600"}`} />
              <span className="text-zinc-500 text-[10px] font-bold uppercase tracking-[0.2em]">
                {systemOnline ? "All Infrastructure Operational" : "System Alert Active"}
              </span>
            </div>
            <h1 className="text-4xl font-extrabold tracking-tight mb-2">DevOps Intelligence</h1>
            <p className="text-zinc-400 text-sm font-medium">
              {health?.current_time ?? new Date().toLocaleTimeString()} · {health?.timezone ?? "Local Time"}
            </p>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <KpiBox label="Resolved" value={`${resolvedPct}%`} />
            <KpiBox label="Open Issues" value={openIssues} />
            <KpiBox label="RCA Done" value={rcaDone} />
            <a
              href="http://localhost:3001/d/server-monitoring"
              target="_blank"
              rel="noopener noreferrer"
              className="bg-white text-gray-900 px-4 py-2.5 rounded-xl text-sm font-bold hover:bg-gray-100 transition-colors shadow"
            >
              📊 Live Grafana
            </a>
          </div>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon="📦" label="Metric Batches" value={metricsTotal} sub="Prometheus batches ingested" />
        <StatCard icon="⚡" label="Total Anomalies" value={anomaliesTotal} sub="AI-detected deviations" />
        <StatCard icon="🔍" label="Open Issues" value={openIssues} sub="Unresolved anomalies" />
        <StatCard icon="✅" label="RCA Complete" value={rcaDone} sub={`${resolvedPct}% resolution rate`} />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Rolling trend chart — real poll data */}
        <div className="bg-white border border-gray-200 rounded-2xl p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-bold text-gray-900">Live Metric Ingestion</h3>
              <p className="text-xs text-gray-500 mt-0.5">Total batches collected (live DB poll)</p>
            </div>
            <span className="flex items-center gap-1.5 text-xs font-semibold bg-gray-100 text-gray-700 px-2.5 py-1 rounded-full border border-gray-200">
              <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" /> Live · 5s
            </span>
          </div>
          {history.length < 2 ? (
            <div className="flex items-center justify-center h-44 text-sm text-gray-400">Collecting data…</div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={history}>
                <defs>
                  <linearGradient id="mgGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#111827" stopOpacity={0.12} />
                    <stop offset="95%" stopColor="#111827" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                <XAxis dataKey="time" tick={{ fontSize: 10, fill: "#9ca3af" }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid #e5e7eb", fontSize: 12 }} labelStyle={{ color: "#111827", fontWeight: 700 }} />
                <Area type="monotone" dataKey="metrics" name="Metric Batches" stroke="#111827" strokeWidth={2} fill="url(#mgGrad)" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* KPI comparison bar — real DB data */}
        <div className="bg-white border border-gray-200 rounded-2xl p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-bold text-gray-900">System Snapshot</h3>
              <p className="text-xs text-gray-500 mt-0.5">Current counts from database</p>
            </div>
            <span className="text-xs font-semibold bg-black text-white px-2.5 py-1 rounded-full">DB</span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={kpiBar} barSize={30}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid #e5e7eb", fontSize: 12 }} labelStyle={{ color: "#111827", fontWeight: 700 }} />
              <Bar dataKey="value" fill="#111827" radius={[5, 5, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Anomaly trend */}
      {history.length >= 2 && (
        <div className="bg-white border border-gray-200 rounded-2xl p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-bold text-gray-900">Anomaly Trend</h3>
              <p className="text-xs text-gray-500 mt-0.5">Open issues vs resolved (live DB)</p>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={170}>
            <AreaChart data={history.slice(-12)}>
              <defs>
                <linearGradient id="openGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#374151" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#374151" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="rcaGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#9ca3af" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#9ca3af" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis dataKey="time" tick={{ fontSize: 10, fill: "#9ca3af" }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 10, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid #e5e7eb", fontSize: 12 }} />
              <Area type="monotone" dataKey="open" name="Open Issues" stroke="#374151" strokeWidth={2} fill="url(#openGrad)" dot={false} />
              <Area type="monotone" dataKey="rca" name="RCA Done" stroke="#9ca3af" strokeWidth={2} fill="url(#rcaGrad)" dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Components + Notifications */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-white border border-gray-200 rounded-2xl p-5">
          <h3 className="font-bold text-gray-900 mb-4">System Components</h3>
          <div className="space-y-3">
            {compHealth.map((c) => (
              <div key={c.label} className="flex items-center justify-between p-3 rounded-xl bg-gray-50 border border-gray-100">
                <div className="flex items-center gap-3">
                  <span className={`w-2.5 h-2.5 rounded-full ${c.ok ? "bg-green-400 animate-pulse" : "bg-gray-300"}`} />
                  <span className="text-sm font-semibold text-gray-900">{c.label}</span>
                </div>
                <span className={`text-xs font-bold px-2.5 py-1 rounded-full border ${c.ok ? "bg-black text-white border-black" : "bg-gray-100 text-gray-500 border-gray-200"}`}>
                  {c.ok ? "Healthy" : "Offline"}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-2xl p-5">
          <h3 className="font-bold text-gray-900 mb-4">Alert Channels</h3>
          <div className="space-y-3">
            <AlertRow icon="📧" label="Email Alerts" ok={emailEnabled}
              sub={emailEnabled ? `${stats?.notifications?.email?.recipients ?? 0} recipient(s)` : "Not configured"} />
            <AlertRow icon="💬" label="Slack Alerts" ok={slackEnabled}
              sub={slackEnabled ? "Webhook configured" : "Not configured"} />
          </div>
        </div>
      </div>
    </div>
  );
}

function KpiBox({ label, value }) {
  return (
    <div className="bg-white/10 border border-white/20 rounded-xl px-4 py-2.5 text-center">
      <p className="text-gray-400 text-xs uppercase tracking-wide">{label}</p>
      <p className="text-white font-bold text-lg mt-0.5">{value}</p>
    </div>
  );
}

function StatCard({ icon, label, value, sub }) {
  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-5 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-3">
        <span className="text-2xl">{icon}</span>
        <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse mt-1" />
      </div>
      <p className="text-sm text-gray-500">{label}</p>
      <p className="text-3xl font-extrabold text-gray-900 mt-1">{value}</p>
      <p className="text-xs text-gray-400 mt-1">{sub}</p>
    </div>
  );
}

function AlertRow({ icon, label, ok, sub }) {
  return (
    <div className={`flex items-center gap-4 p-4 rounded-xl border ${ok ? "border-gray-200 bg-gray-50" : "border-gray-100 bg-white"}`}>
      <span className="text-2xl">{icon}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="font-semibold text-gray-900 text-sm">{label}</p>
          <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${ok ? "bg-black text-white" : "bg-gray-100 text-gray-600"}`}>
            {ok ? "ACTIVE" : "OFF"}
          </span>
        </div>
        <p className="text-xs text-gray-500 mt-0.5">{sub}</p>
      </div>
      <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${ok ? "bg-green-400 animate-pulse" : "bg-gray-300"}`} />
    </div>
  );
}

