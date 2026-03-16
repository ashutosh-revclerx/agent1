import { useState, useEffect } from "react";
import { api } from "../services/api";
import { formatDateTime } from "../utils/time";

export default function MetricsOverview() {
  const [metrics, setMetrics] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  const fetchData = async () => {
    try {
      const metricsData = await api.getBatches();
      setMetrics(metricsData.batches || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-10 w-10 border-2 border-blue-200 border-t-blue-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white border border-blue-100 rounded-xl p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-gray-900">
              Metrics Overview
            </h2>
            <p className="text-sm text-gray-600 mt-1">
              View all collected metrics batches
            </p>
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-white border border-red-200 rounded-xl p-4">
          <p className="text-red-700 text-sm">{error}</p>
        </div>
      )}

      {/* Metrics List */}
      <div className="bg-white border border-blue-100 rounded-xl p-6">
        <h3 className="text-base font-semibold text-gray-900 mb-4">
          Metrics Batches ({metrics.length})
        </h3>

        {metrics.length === 0 ? (
          <p className="text-sm text-gray-500 text-center py-8">
            No metrics found.
          </p>
        ) : (
          <div className="space-y-3">
            {metrics.map((batch, idx) => (
              <MetricsBatchCard key={batch._id || idx} batch={batch} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function MetricsBatchCard({ batch }) {
  const [expanded, setExpanded] = useState(false);

  const formatTime = (timestamp) => {
    return formatDateTime(timestamp);
  };

  // Derive a meaningful title: prefer instance from first metric, fall back to window times
  const firstMetricInstance = batch.metrics?.[0]?.instance;
  const metricsCount = batch.metrics?.length || batch.metrics_count || 0;

  // Build a readable title
  const title = firstMetricInstance
    ? firstMetricInstance
    : batch.window_start
    ? `Batch ${formatTime(batch.window_start)}`
    : "Batch Analysis";

  const subtitle = batch.window_start && batch.window_end
    ? `${formatTime(batch.window_start)} → ${formatTime(batch.window_end)} • ${metricsCount} metrics`
    : `${formatTime(batch.collected_at)} • ${metricsCount} metrics`;

  const handleViewGrafana = async (e) => {
    e.stopPropagation();
    const instance = firstMetricInstance || batch.instance;
    if (!instance) {
      alert('No instance information available for this batch');
      return;
    }
    try {
      const { grafana_url } = await api.getGrafanaUrl(instance);
      window.open(grafana_url, '_blank');
    } catch (error) {
      console.error('Failed to get Grafana URL:', error);
      alert('Failed to open Grafana. Make sure Grafana is running.');
    }
  };

  return (
    <div className="border border-blue-100 rounded-lg overflow-hidden">
      <div
        className="p-4 hover:bg-blue-50 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="font-semibold text-gray-900">{title}</p>
            <p className="text-xs text-gray-500 mt-1">{subtitle}</p>
          </div>
          <div className="flex items-center gap-2">
            {firstMetricInstance && (
              <button
                onClick={handleViewGrafana}
                className="px-3 py-1.5 bg-blue-600 text-white text-xs font-semibold rounded hover:bg-blue-700 transition-colors"
              >
                📊 Grafana
              </button>
            )}
            <span className="text-sm text-blue-600">
              {expanded ? "▼" : "▶"}
            </span>
          </div>
        </div>
      </div>

      {expanded && batch.metrics && (
        <div className="border-t border-blue-100 bg-blue-50/30 p-4">
          <div className="max-h-96 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="bg-white sticky top-0">
                <tr className="border-b border-blue-100">
                  <th className="text-left p-2 font-semibold text-gray-700">
                    Metric Name
                  </th>
                  <th className="text-left p-2 font-semibold text-gray-700">
                    Value
                  </th>
                  <th className="text-left p-2 font-semibold text-gray-700">
                    Instance
                  </th>
                </tr>
              </thead>
              <tbody>
                {batch.metrics.map((metric, idx) => (
                  <tr
                    key={idx}
                    className={idx % 2 === 0 ? "bg-white" : "bg-blue-50/50"}
                  >
                    <td className="p-2 text-gray-900">{metric.name || "—"}</td>
                    <td className="p-2 text-gray-700">
                      {typeof metric.value === "number"
                        ? metric.value.toFixed(4)
                        : metric.value ?? "—"}
                    </td>
                    <td className="p-2 text-gray-600 text-xs">
                      {metric.instance || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
