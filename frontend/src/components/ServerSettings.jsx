import { useState, useEffect } from 'react';
import { api } from '../services/api';
import { Spinner } from './shared';

export default function ServerSettings() {
  const [targets, setTargets] = useState([]);
  const [newTarget, setNewTarget] = useState({ name: '', endpoint: '' });
  const [slackConfig, setSlackConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [msg, setMsg] = useState(null);
  const [slackTestSending, setSlackTestSending] = useState(false);

  useEffect(() => { fetchData(); }, []);

  const fetchData = async () => {
    try {
      const [tData, sData] = await Promise.all([
        api.getTargets(),
        api.getSlackConfig(),
      ]);
      setTargets(tData);
      setSlackConfig(sData);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleAddServer = async (e) => {
    e.preventDefault();
    if (!newTarget.name || !newTarget.endpoint) return;
    try {
      await api.addTarget(newTarget);
      setNewTarget({ name: '', endpoint: '' });
      await fetchData();
      flashMsg('success', 'Server added successfully');
    } catch (err) {
      setError(err.message);
    }
  };

  const handleRemoveServer = async (endpoint) => {
    if (!window.confirm(`Remove server ${endpoint}?`)) return;
    try {
      await api.removeTarget(endpoint);
      await fetchData();
      flashMsg('success', 'Server removed');
    } catch (err) {
      setError(err.message);
    }
  };

  const handleSlackSave = async () => {
    try {
      await api.updateSlackConfig(slackConfig);
      flashMsg('success', 'Slack configuration saved');
    } catch (err) {
      setError(err.message);
    }
  };

  const handleSlackTest = async () => {
    setSlackTestSending(true);
    try {
      await api.sendTestSlack();
      flashMsg('success', 'Test alert sent to Slack!');
    } catch (err) {
      setError(err.message);
    } finally {
      setSlackTestSending(false);
    }
  };

  const flashMsg = (type, text) => {
    setMsg({ type, text });
    setTimeout(() => setMsg(null), 3500);
  };

  const activeCount = targets.filter((t) => t.enabled).length;
  const slackActive = slackConfig?.enabled && slackConfig?.webhook_url;

  if (loading) {
    return <Spinner />;
  }

  return (
    <div className="space-y-5">
      {/* Hero */}
      <div className="bg-gray-900 rounded-2xl p-6 text-white">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
              <span className="text-gray-400 text-xs font-semibold uppercase tracking-widest">
                Infrastructure Control
              </span>
            </div>
            <h1 className="text-2xl font-bold">Server Management</h1>
            <p className="text-gray-400 text-sm mt-1">
              Configure monitored servers and alert integrations
            </p>
          </div>
          <div className="flex gap-3 flex-wrap">
            <KpiChip label="Monitored Servers" value={targets.length} />
            <KpiChip label="Active" value={activeCount} />
            <KpiChip label="Slack" value={slackActive ? "ON" : "OFF"} warn={!slackActive} />
          </div>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-2xl p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-red-500 text-lg">⚠</span>
            <p className="text-red-700 text-sm font-medium">{error}</p>
          </div>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600 font-bold text-lg w-6 h-6 flex items-center justify-center">×</button>
        </div>
      )}
      {msg && (
        <div className={`rounded-2xl p-4 flex items-center gap-3 border ${
          msg.type === 'success'
            ? 'bg-green-50 border-green-200 text-green-700'
            : 'bg-gray-50 border-gray-200 text-gray-700'
        }`}>
          <span className="text-lg">{msg.type === 'success' ? '✓' : 'ℹ'}</span>
          <p className="text-sm font-semibold">{msg.text}</p>
        </div>
      )}

      {/* Infrastructure Overview */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon="🖥️" label="Total Servers" value={targets.length} />
        <StatCard icon="✅" label="Active" value={activeCount} />
        <StatCard icon="⏸️" label="Disabled" value={targets.length - activeCount} />
        <StatCard icon="💬" label="Slack Webhook" value={slackActive ? "Configured" : "Not set"} small />
      </div>

      {/* Add Server */}
      <div className="bg-white border border-gray-200 rounded-2xl p-6">
        <div className="flex items-center gap-3 mb-5">
          <div className="w-10 h-10 rounded-xl bg-gray-900 flex items-center justify-center text-white text-xl">
            ➕
          </div>
          <div>
            <h3 className="text-lg font-bold text-gray-900">Add New Server</h3>
            <p className="text-xs text-gray-500 mt-0.5">Register a Prometheus-compatible endpoint</p>
          </div>
        </div>
        <form onSubmit={handleAddServer} className="flex flex-col md:flex-row gap-3">
          <div className="flex-1">
            <label className="block text-xs font-bold text-gray-600 mb-1.5 uppercase tracking-wider">
              Server Name
            </label>
            <input
              type="text"
              placeholder="e.g. Prod DB, App Server"
              className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-gray-900 focus:border-gray-900 focus:outline-none"
              value={newTarget.name}
              onChange={(e) => setNewTarget({ ...newTarget, name: e.target.value })}
              required
            />
          </div>
          <div className="flex-1">
            <label className="block text-xs font-bold text-gray-600 mb-1.5 uppercase tracking-wider">
              Endpoint
            </label>
            <input
              type="text"
              placeholder="e.g. 192.168.1.5:9100"
              className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm font-mono focus:ring-2 focus:ring-gray-900 focus:border-gray-900 focus:outline-none"
              value={newTarget.endpoint}
              onChange={(e) => setNewTarget({ ...newTarget, endpoint: e.target.value })}
              required
            />
          </div>
          <div className="flex items-end">
            <button
              type="submit"
              className="w-full md:w-auto bg-gray-900 text-white px-6 py-2.5 rounded-xl hover:bg-black transition-colors font-bold text-sm"
            >
              Add Server
            </button>
          </div>
        </form>
      </div>

      {/* Full Server Table */}
      <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100 bg-gray-50 flex items-center justify-between">
          <div>
            <h3 className="font-bold text-gray-900">Monitored Servers</h3>
            <p className="text-xs text-gray-500 mt-0.5">All registered Prometheus scrape targets</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold bg-black text-white px-2.5 py-1 rounded-full">
              {targets.length} total
            </span>
            <span className="text-xs font-bold bg-green-50 text-green-700 border border-green-200 px-2.5 py-1 rounded-full">
              {activeCount} active
            </span>
          </div>
        </div>

        {targets.length === 0 ? (
          <div className="p-12 text-center">
            <p className="text-4xl mb-3">🖥️</p>
            <p className="text-gray-500 font-semibold">No servers configured yet.</p>
            <p className="text-sm text-gray-400 mt-1">Add one above to start monitoring.</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {targets.map((t) => (
              <div key={t.endpoint} className="px-6 py-4 flex items-center justify-between hover:bg-gray-50 transition-colors">
                <div className="flex items-center gap-4">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-lg ${
                    t.enabled ? 'bg-gray-900' : 'bg-gray-100'
                  }`}>
                    🖥️
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-gray-900">{t.name}</span>
                      <span className={`text-xs font-extrabold px-2 py-0.5 rounded-full ${
                        t.enabled
                          ? 'bg-black text-white border border-black'
                          : 'bg-gray-100 text-gray-500 border border-gray-200'
                      }`}>
                        {t.enabled ? 'ACTIVE' : 'DISABLED'}
                      </span>
                    </div>
                    <p className="text-xs font-mono text-gray-500 mt-0.5">{t.endpoint}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className={`w-2.5 h-2.5 rounded-full ${t.enabled ? 'bg-green-400 animate-pulse' : 'bg-gray-300'}`} />
                  <button
                    onClick={() => handleRemoveServer(t.endpoint)}
                    className="text-xs font-bold text-red-500 hover:text-red-700 px-3 py-1.5 rounded-xl hover:bg-red-50 border border-transparent hover:border-red-200 transition-all"
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Slack Integration */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <div className="flex items-center gap-3 mb-5">
          <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center text-2xl">
            💬
          </div>
          <div>
            <h3 className="text-lg font-bold text-gray-900">Slack Integration</h3>
            <p className="text-xs text-gray-500 mt-0.5">Real-time anomaly alerts via Slack webhook</p>
          </div>
          {slackActive && (
            <span className="ml-auto text-xs font-bold bg-green-50 text-green-700 border border-green-200 px-2.5 py-1 rounded-full flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
              Connected
            </span>
          )}
        </div>

        {slackConfig && (
          <div className="space-y-4">
            {/* Toggle */}
            <div className="flex items-center justify-between p-4 rounded-xl bg-gray-50 border border-gray-200">
              <div>
                <p className="font-semibold text-gray-900 text-sm">Enable Slack Alerts</p>
                <p className="text-xs text-gray-500 mt-0.5">
                  {slackConfig.enabled
                    ? 'Anomaly alerts will be posted to Slack'
                    : 'Slack notifications are disabled'}
                </p>
              </div>
              <button
                onClick={() => setSlackConfig({ ...slackConfig, enabled: !slackConfig.enabled })}
                className={`relative w-12 h-6 rounded-full transition-colors focus:outline-none ${
                  slackConfig.enabled ? 'bg-gray-900' : 'bg-gray-300'
                }`}
              >
                <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                  slackConfig.enabled ? 'translate-x-6' : 'translate-x-0'
                }`} />
              </button>
            </div>

            {/* Webhook URL */}
            <div>
              <label className="block text-xs font-bold text-gray-600 mb-1.5 uppercase tracking-wider">
                Webhook URL
              </label>
              <input
                type="password"
                value={slackConfig.webhook_url}
                onChange={(e) => setSlackConfig({ ...slackConfig, webhook_url: e.target.value })}
                placeholder="https://hooks.slack.com/services/…"
                className="w-full border border-gray-200 rounded-xl px-4 py-2.5 font-mono text-sm focus:ring-2 focus:ring-gray-900 focus:border-gray-900 focus:outline-none"
              />
              <p className="text-xs text-gray-400 mt-1.5">
                Your webhook URL is stored securely and never displayed in plain text.
              </p>
            </div>

            <div className="flex items-center gap-3 pt-1">
              <button
                onClick={handleSlackSave}
                className="bg-gray-900 text-white px-5 py-2.5 rounded-xl hover:bg-black transition-colors font-bold text-sm"
              >
                Save Configuration
              </button>
              {slackConfig.enabled && slackConfig.webhook_url && (
                <button
                  onClick={handleSlackTest}
                  disabled={slackTestSending}
                  className="border border-gray-300 text-gray-700 px-5 py-2.5 rounded-xl hover:bg-gray-50 transition-colors font-bold text-sm disabled:opacity-60"
                >
                  {slackTestSending ? '⟳ Sending…' : '🧪 Send Test Alert'}
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function KpiChip({ label, value, warn = false }) {
  return (
    <div className={`rounded-xl px-3 py-2 text-center border ${
      warn ? 'bg-white/20 border-yellow-300/40' : 'bg-white/15 border-white/20'
    }`}>
      <p className="text-gray-400 text-xs uppercase tracking-wide">{label}</p>
      <p className={`font-extrabold text-lg ${warn ? 'text-yellow-300' : 'text-white'}`}>{value}</p>
    </div>
  );
}

function StatCard({ icon, label, value, small }) {
  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-4 hover:shadow-md transition-shadow">
      <div className="flex items-center gap-3">
        <span className="text-2xl">{icon}</span>
        <div>
          <p className="text-xs text-gray-500">{label}</p>
          <p className={`font-extrabold text-gray-900 ${small ? 'text-base' : 'text-2xl'} mt-0.5`}>
            {value}
          </p>
        </div>
      </div>
    </div>
  );
}

