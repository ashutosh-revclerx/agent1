import { useState, useEffect, useMemo } from "react";
import { api } from "../services/api";
import { Spinner, SummaryCard } from "./shared";
import { formatDateTime } from "../utils/time";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer, LineChart, Line, ReferenceLine,
} from "recharts";

export default function MetricsOverview() {
  const [metrics, setMetrics] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  const fetchData = async () => {
    try {
      const data = await api.getBatches();
      setMetrics(data.batches || []);
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const filtered = useMemo(() => {
    if (!search.trim()) return metrics;
    const q = search.toLowerCase();
    return metrics.filter((b) => (b.metrics?.[0]?.instance || "").toLowerCase().includes(q));
  }, [metrics, search]);

  const totalMetricPoints = useMemo(
    () => metrics.reduce((s, b) => s + (b.metrics?.length || b.metrics_count || 0), 0),
    [metrics]
  );

  const avgPerBatch = metrics.length > 0 ? Math.round(totalMetricPoints / metrics.length) : 0;

  const batchSizeChart = useMemo(
    () =>
      metrics.slice(0, 14).map((b, i) => ({
        name: `B${i + 1}`,
        metrics: b.metrics?.length || b.metrics_count || 0,
        label: b.metrics?.[0]?.instance || `Batch ${i + 1}`,
      })),
    [metrics]
  );

  if (loading) return <Spinner />;

  return (
    <div className="space-y-5">
      {/* Hero */}
      <div className="bg-gray-900 rounded-2xl p-6 text-white">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
              <span className="text-gray-400 text-xs font-semibold uppercase tracking-widest">Auto-refresh · 10s</span>
            </div>
            <h1 className="text-2xl font-bold">Metrics Overview</h1>
            <p className="text-gray-400 text-sm mt-1">Prometheus batch ingestion &amp; historical analysis</p>
          </div>
          <div className="flex gap-3 flex-wrap items-center">
            <KpiBox label="Total Batches" value={metrics.length} />
            <KpiBox label="Metric Points" value={totalMetricPoints.toLocaleString()} />
            <KpiBox label="Avg / Batch" value={avgPerBatch} />
            <button onClick={fetchData} className="bg-white text-gray-900 px-4 py-2.5 rounded-xl text-sm font-bold hover:bg-gray-100 shadow">↻ Refresh</button>
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-center gap-3">
          <span className="text-red-500">⚠</span>
          <p className="text-red-700 text-sm">{error}</p>
        </div>
      )}

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <SummaryCard icon="📦" label="Total Batches" value={metrics.length} />
        <SummaryCard icon="📊" label="Metric Points" value={totalMetricPoints.toLocaleString()} />
        <SummaryCard icon="📐" label="Avg / Batch" value={avgPerBatch} />
        <SummaryCard icon="🕐" label="Last Updated" value={lastUpdated ? lastUpdated.toLocaleTimeString() : "—"} small />
      </div>

      {/* Batch size chart */}
      {batchSizeChart.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-2xl p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-bold text-gray-900">Batch Size Distribution</h3>
              <p className="text-xs text-gray-500 mt-0.5">Metric count per ingestion batch (latest {batchSizeChart.length})</p>
            </div>
            <span className="text-xs font-bold bg-black text-white px-2.5 py-1 rounded-full">DB</span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={batchSizeChart} barSize={22}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ borderRadius: 8, border: "1px solid #e5e7eb", fontSize: 12 }}
                labelStyle={{ color: "#111827", fontWeight: 700 }}
                formatter={(v, _, p) => [v, p.payload?.label || "Metrics"]}
              />
              <ReferenceLine y={avgPerBatch} stroke="#9ca3af" strokeDasharray="4 4" label={{ value: "Avg", fill: "#6b7280", fontSize: 10 }} />
              <Bar dataKey="metrics" fill="#111827" radius={[5, 5, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Batch list */}
      <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between gap-3 flex-wrap bg-gray-50">
          <div>
            <h3 className="font-bold text-gray-900">
              Metrics Batches <span className="text-gray-900 font-extrabold">({filtered.length})</span>
            </h3>
            <p className="text-xs text-gray-500 mt-0.5">Click any batch to expand metrics detail</p>
          </div>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter by instance…"
            className="border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900 w-52"
          />
        </div>
        {filtered.length === 0 ? (
          <div className="p-12 text-center">
            <p className="text-3xl mb-3">📭</p>
            <p className="text-gray-500 font-medium">{search ? "No batches match." : "No metrics batches found."}</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {filtered.map((batch, idx) => (
              <MetricsBatchCard key={batch._id || idx} batch={batch} index={idx} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function MetricsBatchCard({ batch, index }) {
  const [expanded, setExpanded] = useState(false);
  const firstMetricInstance = batch.metrics?.[0]?.instance;
  const metricsCount = batch.metrics?.length || batch.metrics_count || 0;

  const title = firstMetricInstance
    ? firstMetricInstance
    : batch.window_start
    ? `Batch ${formatDateTime(batch.window_start)}`
    : "Batch Analysis";

  const subtitle =
    batch.window_start && batch.window_end
      ? `${formatDateTime(batch.window_start)} → ${formatDateTime(batch.window_end)} • ${metricsCount} metrics`
      : `${formatDateTime(batch.collected_at)} • ${metricsCount} metrics`;

  const handleViewGrafana = async (e) => {
    e.stopPropagation();
    const instance = firstMetricInstance || batch.instance;
    if (!instance) { alert("No instance information available"); return; }
    try {
      const { grafana_url } = await api.getGrafanaUrl(instance);
      window.open(grafana_url, "_blank");
    } catch { alert("Failed to open Grafana."); }
  };

  const sparkData = useMemo(() => {
    if (!batch.metrics) return [];
    return batch.metrics
      .filter((m) => typeof m.value === "number")
      .slice(0, 20)
      .map((m, i) => ({ i, v: m.value }));
  }, [batch.metrics]);

  return (
    <div className={`transition-colors ${expanded ? "bg-gray-50" : "hover:bg-gray-50/50"}`}>
      <div className="px-6 py-4 cursor-pointer flex items-center gap-4" onClick={() => setExpanded(!expanded)}>
        <div className="w-9 h-9 rounded-full bg-gray-100 text-gray-700 font-bold text-sm flex items-center justify-center flex-shrink-0">
          {index + 1}
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-gray-900 truncate">{title}</p>
          <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>
        </div>
        {sparkData.length > 3 && (
          <div className="hidden md:block w-28 h-10 flex-shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sparkData}>
                <Line type="monotone" dataKey="v" stroke="#374151" dot={false} strokeWidth={1.5} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="hidden sm:inline text-xs font-bold bg-gray-100 text-gray-700 border border-gray-200 px-2.5 py-1 rounded-full">
            {metricsCount} pts
          </span>
          {firstMetricInstance && (
            <button
              onClick={handleViewGrafana}
              className="px-3 py-1.5 bg-gray-900 text-white text-xs font-bold rounded-lg hover:bg-black transition-colors"
            >
              📊 Grafana
            </button>
          )}
          <span className="text-gray-500 text-sm font-bold">{expanded ? "▾" : "▸"}</span>
        </div>
      </div>
      {expanded && batch.metrics && (
        <div className="px-6 pb-5">
          <div className="border border-gray-200 rounded-xl overflow-hidden">
            <div className="bg-gray-900 px-4 py-2.5 flex items-center justify-between">
              <span className="text-white font-semibold text-sm">Metric Values ({batch.metrics.length})</span>
              <span className="text-gray-400 text-xs">Instance: {firstMetricInstance || "—"}</span>
            </div>
            <div className="max-h-80 overflow-y-auto bg-white">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-gray-50 border-b border-gray-100">
                  <tr>
                    <th className="text-left p-3 font-bold text-gray-700 text-xs uppercase tracking-wider">Metric</th>
                    <th className="text-left p-3 font-bold text-gray-700 text-xs uppercase tracking-wider">Value</th>
                    <th className="text-left p-3 font-bold text-gray-700 text-xs uppercase tracking-wider">Instance</th>
                    <th className="text-left p-3 font-bold text-gray-700 text-xs uppercase tracking-wider w-32">Bar</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {batch.metrics.map((metric, idx) => {
                    const maxVal = Math.max(...batch.metrics.filter((m) => typeof m.value === "number").map((m) => m.value), 1);
                    const barPct = typeof metric.value === "number" ? Math.round((metric.value / maxVal) * 100) : 0;
                    return (
                      <tr key={idx} className="hover:bg-gray-50 transition-colors">
                        <td className="p-3 font-mono text-xs text-gray-800">{metric.name || "—"}</td>
                        <td className="p-3 font-bold text-gray-900 font-mono text-xs">
                          {typeof metric.value === "number" ? metric.value.toFixed(4) : metric.value ?? "—"}
                        </td>
                        <td className="p-3 text-gray-500 text-xs truncate max-w-xs">{metric.instance || "—"}</td>
                        <td className="p-3 w-32">
                          <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                            <div className="h-full bg-gray-700 rounded-full" style={{ width: `${barPct}%` }} />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
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

