import { useState, useEffect, useMemo } from "react";
import { api } from "../services/api";
import { Spinner, SummaryCard } from "./shared";
import { formatDateTime } from "../utils/time";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer, Cell,
} from "recharts";

const STATUS_COLORS = ["#111827", "#374151", "#6b7280", "#9ca3af", "#d1d5db"];

export default function RCAResults() {
  const [rcaResults, setRcaResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [activeRca, setActiveRca] = useState(null);

  useEffect(() => {
    fetchRCA(true);
    const interval = setInterval(() => fetchRCA(false), 15000);
    return () => clearInterval(interval);
  }, []);

  const fetchRCA = async (initial = false) => {
    try {
      if (initial) setLoading(true);
      else setRefreshing(true);
      const data = await api.getRCA();
      setRcaResults(data?.rca || []);
      setError(null);
    } catch (err) {
      setError(err?.message || "Failed to load RCA results");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const total = rcaResults.length;

  const topMetrics = useMemo(() => {
    const map = {};
    for (const r of rcaResults) {
      const m = r?.metric || "Batch Analysis";
      map[m] = (map[m] || 0) + 1;
    }
    return Object.entries(map)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([name, count], i) => ({
        name: name.length > 22 ? name.slice(0, 20) + "…" : name,
        count,
        color: STATUS_COLORS[i % STATUS_COLORS.length],
      }));
  }, [rcaResults]);

  if (loading) {
    return <Spinner />;
  }

  if (error) {
    return (
      <div className="bg-white border border-gray-200 rounded-xl p-6">
        <p className="text-gray-900 font-semibold mb-1">Failed to load RCA results</p>
        <p className="text-sm text-gray-600 mb-4">{error}</p>
        <button
          onClick={() => fetchRCA(true)}
          className="px-4 py-2 bg-gray-900 text-white rounded-lg hover:bg-black font-semibold text-sm"
        >
          Retry
        </button>
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
              <span className="text-gray-400 text-xs font-semibold uppercase tracking-widest">
                Auto-refresh · 15s
              </span>
            </div>
            <h1 className="text-2xl font-bold">RCA Results</h1>
            <p className="text-gray-400 text-sm mt-1">
              AI-generated root cause analysis and remediation
            </p>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <KpiChip label="Total Reports" value={total} />
            <KpiChip label="Metrics Analyzed" value={topMetrics.length} />
            <button
              onClick={() => fetchRCA(false)}
              disabled={refreshing}
              className="bg-white text-gray-900 px-4 py-2.5 rounded-xl text-sm font-bold hover:bg-gray-100 shadow disabled:opacity-60 transition-colors"
            >
              {refreshing ? "↻ Refreshing…" : "↻ Refresh"}
            </button>
          </div>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <SummaryCard icon="🔍" label="Total RCA Reports" value={total} />
        <SummaryCard icon="⚙️" label="Metrics Covered" value={topMetrics.length} />
        <SummaryCard
          icon="🛠️"
          label="Latest Analysis"
          value={rcaResults[0]?.timestamp ? new Date(rcaResults[0].timestamp).toLocaleDateString() : "—"}
          small
        />
        <SummaryCard icon="🤖" label="AI Confidence" value="High" small />
      </div>

      {/* Chart */}
      {topMetrics.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-2xl p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-bold text-gray-900">RCA Frequency by Metric</h3>
              <p className="text-xs text-gray-500 mt-0.5">Which metrics triggered root-cause analysis most</p>
            </div>
            <span className="text-xs font-bold bg-black text-white px-2.5 py-1 rounded-full">
              {total} total
            </span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={topMetrics} layout="vertical" barSize={16}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 10, fill: "#6b7280" }} axisLine={false} tickLine={false} width={130} />
              <Tooltip
                contentStyle={{ borderRadius: 8, border: "1px solid #e5e7eb", fontSize: 12 }}
                labelStyle={{ color: "#111827", fontWeight: 700 }}
              />
              <Bar dataKey="count" radius={[0, 5, 5, 0]}>
                {topMetrics.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* RCA Cards */}
      <div className="bg-white border border-gray-200 rounded-2xl">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <div>
            <h3 className="font-bold text-gray-900">
              RCA Reports <span className="text-gray-900 font-extrabold">({total})</span>
            </h3>
            <p className="text-xs text-gray-500 mt-0.5">Click &quot;Ask AI&quot; to deep-dive into any report</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
            <span className="text-xs text-gray-500">Live</span>
          </div>
        </div>

        {rcaResults.length === 0 ? (
          <div className="p-12 text-center">
            <p className="text-4xl mb-3">🔬</p>
            <p className="text-gray-800 font-bold text-lg">No RCA results yet</p>
            <p className="text-sm text-gray-500 mt-1">
              Reports appear once anomalies are analyzed by the AI engine.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100 p-4 space-y-3">
            {rcaResults.map((rca, idx) => (
              <RcaCard
                key={rca?._id || idx}
                rca={rca}
                onAsk={() => { setActiveRca(rca); setChatOpen(true); }}
              />
            ))}
          </div>
        )}
      </div>

      {rcaResults.length > 0 && (
        <p className="text-center text-xs text-gray-400 pb-2">
          ↻ Auto-refreshing every 15 seconds
        </p>
      )}

      {chatOpen && activeRca && (
        <ChatModal rca={activeRca} onClose={() => setChatOpen(false)} />
      )}
    </div>
  );
}

function RcaCard({ rca, onAsk }) {
  const [expanded, setExpanded] = useState(false);
  const metric   = rca?.metric || "Batch Analysis";
  const instance = rca?.instance;
  const summary  = rca?.summary;
  const cause    = rca?.cause || "Analysis in progress…";
  const fix      = Array.isArray(rca?.fix) ? rca.fix : rca?.fix ? [rca.fix] : ["Recommendations pending…"];
  const ts       = rca?.timestamp ? new Date(rca.timestamp) : null;
  const tsText   = ts ? formatDateTime(ts) : "—";

  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-5 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="px-2.5 py-1 rounded-full text-xs font-extrabold border bg-black text-white border-black">
              RCA
            </span>
            <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-green-50 text-green-700 border border-green-200">
              COMPLETE
            </span>
            <h3 className="font-bold text-gray-900 truncate">{metric}</h3>
          </div>

          {instance && (
            <p className="text-xs text-gray-500 mt-2">
              <span className="font-bold text-gray-700">Instance:</span>{" "}
              <span className="font-mono break-all">{instance}</span>
            </p>
          )}

          {summary && (
            <div className="mt-3 bg-gray-50 border border-gray-200 rounded-xl px-4 py-2.5">
              <p className="text-xs font-bold text-gray-600 uppercase tracking-wider mb-0.5">Summary</p>
              <p className="text-sm text-gray-800">{summary}</p>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={() => setExpanded(!expanded)}
            className="px-3 py-2 rounded-xl border border-gray-200 text-gray-600 hover:bg-gray-50 text-xs font-bold transition-colors"
          >
            {expanded ? "▾ Less" : "▸ More"}
          </button>
          <button
            onClick={onAsk}
            className="px-3 py-2 rounded-xl bg-gray-900 text-white hover:bg-black text-xs font-bold transition-colors"
          >
            Ask AI
          </button>
        </div>
      </div>

      {/* Root Cause + Fix */}
      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="border-2 border-gray-100 rounded-xl p-4 bg-gray-50/50">
          <p className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-1.5">Root Cause</p>
          <p className="text-sm text-gray-900 leading-relaxed whitespace-pre-wrap">{cause}</p>
        </div>
        <div className="border-2 border-gray-100 rounded-xl p-4">
          <p className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-1.5">Recommended Actions</p>
          <ul className="space-y-1">
            {(Array.isArray(fix) ? fix : [fix]).map((f, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-900">
                <span className="text-gray-500 font-bold flex-shrink-0 mt-0.5">▸</span>
                <span>{f}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="mt-4 pt-4 border-t border-gray-100 grid grid-cols-2 md:grid-cols-4 gap-3">
          {rca?._id && (
            <div className="bg-gray-50 rounded-xl p-3">
              <p className="text-xs text-gray-400 uppercase tracking-wider">RCA ID</p>
              <p className="text-xs font-mono text-gray-700 mt-0.5">{String(rca._id).slice(0, 8)}…</p>
            </div>
          )}
          {rca?.anomaly_id && (
            <div className="bg-gray-50 rounded-xl p-3">
              <p className="text-xs text-gray-400 uppercase tracking-wider">Anomaly</p>
              <p className="text-xs font-mono text-gray-700 mt-0.5">{String(rca.anomaly_id).slice(0, 8)}…</p>
            </div>
          )}
          <div className="bg-gray-50 rounded-xl p-3">
            <p className="text-xs text-gray-400 uppercase tracking-wider">Analyzed At</p>
            <p className="text-xs text-gray-700 mt-0.5">{tsText}</p>
          </div>
          <div className="bg-gray-100 rounded-xl p-3 border border-gray-200">
            <p className="text-xs text-gray-600 uppercase tracking-wider font-bold">Status</p>
            <p className="text-xs font-bold text-gray-900 mt-0.5">Completed ✓</p>
          </div>
        </div>
      )}

      <div className="mt-3 pt-3 border-t border-gray-100 flex items-center justify-between">
        <p className="text-xs text-gray-400">{tsText}</p>
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
          <span className="text-xs text-gray-400">AI analyzed</span>
        </div>
      </div>
    </div>
  );
}

function KpiChip({ label, value }) {
  return (
    <div className="bg-white/15 border border-white/20 rounded-xl px-3 py-2 text-center">
      <p className="text-gray-400 text-xs uppercase tracking-wide">{label}</p>
      <p className="text-white font-extrabold text-lg mt-0.5">{value}</p>
    </div>
  );
}


function ChatModal({ rca, onClose }) {
  const [messages, setMessages] = useState([
    {
      role: "ai",
      text: `Hi! I analyzed the ${rca?.metric || "anomaly"} RCA. What do you want to understand?`,
    },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState(null);

  useEffect(() => {
    const el = document.getElementById("rca-chat-box");
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
        metric: rca?.metric,
        instance: rca?.instance,
        cause: rca?.cause,
        fix: rca?.fix,
        summary: rca?.summary,
        ...(rca?.simplified ? { simplified: rca.simplified } : {}),
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
            <p className="text-xs text-gray-400 truncate max-w-[22rem]">
              {rca?.metric ? `Discussing: ${rca.metric}` : "Discussing RCA"}
            </p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg bg-white/20 text-white hover:bg-white/30 font-bold text-lg flex items-center justify-center"
          >
            ×
          </button>
        </div>

        <div id="rca-chat-box" className="flex-1 overflow-y-auto p-4 space-y-3 bg-white">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[80%] rounded-2xl p-3 text-sm whitespace-pre-wrap ${
                  m.role === "user"
                    ? "bg-gray-900 text-white"
                    : "bg-gray-100 text-gray-900 border border-gray-200"
                }`}
              >
                {m.text}
              </div>
            </div>
          ))}
          {sending && (
            <div className="flex justify-start">
              <div className="bg-gray-100 border border-gray-200 rounded-2xl p-3 text-xs text-gray-500 flex items-center gap-2">
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

