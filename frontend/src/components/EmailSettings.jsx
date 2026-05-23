import { useState, useEffect } from 'react';
import { api } from '../services/api';
import { Spinner } from './shared';

export default function EmailSettings() {
  const [config, setConfig] = useState({ enabled: false, recipients: [] });
  const [newEmail, setNewEmail] = useState('');
  const [message, setMessage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sendingTest, setSendingTest] = useState(false);
  const [activityLog, setActivityLog] = useState([]);

  useEffect(() => {
    fetchConfig();
  }, []);

  const fetchConfig = async () => {
    try {
      const data = await api.getEmailConfig();
      setConfig(data);
      setLoading(false);
    } catch (err) {
      flash('error', err.message);
      setLoading(false);
    }
  };

  const flash = (type, text) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 4000);
  };

  const addActivity = (icon, text) => {
    const entry = { icon, text, ts: new Date().toLocaleTimeString() };
    setActivityLog((prev) => [entry, ...prev].slice(0, 6));
  };

  const toggleEmail = async () => {
    try {
      const newConfig = { ...config, enabled: !config.enabled };
      await api.updateEmailConfig(newConfig);
      setConfig(newConfig);
      flash('success', `Email alerts ${!config.enabled ? 'enabled' : 'disabled'}`);
      addActivity(!config.enabled ? '✅' : '🔕', `Email alerts ${!config.enabled ? 'enabled' : 'disabled'}`);
    } catch (err) {
      flash('error', err.message);
    }
  };

  const addRecipient = async (e) => {
    e.preventDefault();
    if (!newEmail || !newEmail.includes('@')) {
      flash('error', 'Please enter a valid email address');
      return;
    }
    if (config.recipients.includes(newEmail)) {
      flash('error', 'This email is already in the list');
      return;
    }
    try {
      const newConfig = { ...config, recipients: [...config.recipients, newEmail] };
      await api.updateEmailConfig(newConfig);
      setConfig(newConfig);
      addActivity('📧', `Added recipient: ${newEmail}`);
      setNewEmail('');
      flash('success', 'Recipient added');
    } catch (err) {
      flash('error', err.message);
    }
  };

  const deleteRecipient = async (email) => {
    if (!window.confirm(`Remove ${email} from recipients?`)) return;
    try {
      const newConfig = { ...config, recipients: config.recipients.filter((e) => e !== email) };
      await api.updateEmailConfig(newConfig);
      setConfig(newConfig);
      addActivity('🗑️', `Removed recipient: ${email}`);
      flash('success', 'Recipient removed');
    } catch (err) {
      flash('error', err.message);
    }
  };

  const sendTestEmail = async () => {
    if (config.recipients.length === 0) {
      flash('error', 'Please add at least one recipient first');
      return;
    }
    try {
      setSendingTest(true);
      flash('info', 'Sending test email…');
      await api.sendTestEmail();
      flash('success', 'Test email sent! Check your inbox.');
      addActivity('📤', 'Test email dispatched');
    } catch (err) {
      flash('error', err.message);
    } finally {
      setSendingTest(false);
    }
  };

  const recipientCount = config.recipients.length;
  const deliveryRate   = config.enabled && recipientCount > 0 ? 100 : 0;

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
              <span className={`w-2 h-2 rounded-full ${config.enabled ? 'bg-green-400 animate-pulse' : 'bg-yellow-400'}`} />
              <span className="text-gray-400 text-xs font-semibold uppercase tracking-widest">
                Alert Configuration
              </span>
            </div>
            <h1 className="text-2xl font-bold">Email Alerts</h1>
            <p className="text-gray-400 text-sm mt-1">
              Configure email notifications for anomaly alerts
            </p>
          </div>
          <div className="flex gap-3 flex-wrap items-center">
            <KpiChip label="Status" value={config.enabled ? 'Active' : 'Off'} ok={config.enabled} />
            <KpiChip label="Recipients" value={recipientCount} />
            <KpiChip label="Delivery" value={`${deliveryRate}%`} ok={deliveryRate > 0} />
          </div>
        </div>
      </div>

      {/* Toast */}
      {message && (
        <div className={`rounded-2xl p-4 flex items-center gap-3 border ${
          message.type === 'success' ? 'bg-green-50 border-green-200 text-green-700' :
          message.type === 'info'    ? 'bg-gray-50 border-gray-200 text-gray-700' :
                                       'bg-red-50 border-red-200 text-red-700'
        }`}>
          <span className="text-lg font-bold">
            {message.type === 'success' ? '✓' : message.type === 'info' ? 'ℹ' : '✕'}
          </span>
          <p className="text-sm font-semibold">{message.text}</p>
        </div>
      )}

      {/* Summary Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon="📧" label="Email Alerts" value={config.enabled ? 'Enabled' : 'Disabled'} ok={config.enabled} small />
        <StatCard icon="👥" label="Recipients" value={recipientCount} />
        <StatCard icon="📤" label="Delivery" value={`${deliveryRate}%`} ok={deliveryRate > 0} small />
        <StatCard icon="🔔" label="Alert Types" value="Critical & High" small />
      </div>

      {/* Enable / Disable */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-4">
            <div className={`w-12 h-12 rounded-2xl flex items-center justify-center text-2xl ${
              config.enabled ? 'bg-gray-900' : 'bg-gray-200'
            }`}>
              📧
            </div>
            <div>
              <h3 className="font-bold text-gray-900">Email Alert System</h3>
              <p className="text-sm text-gray-500 mt-0.5">
                {config.enabled
                  ? 'Emails are sent for critical and high severity anomalies'
                  : 'Email notifications are currently disabled'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-xs text-gray-400 uppercase tracking-wider">Status</p>
              <p className={`text-sm font-extrabold ${config.enabled ? 'text-green-600' : 'text-gray-400'}`}>
                {config.enabled ? '● Online' : '○ Offline'}
              </p>
            </div>
            <button
              onClick={toggleEmail}
              className={`relative w-14 h-7 rounded-full transition-colors focus:outline-none shadow-inner ${
                config.enabled ? 'bg-gray-900' : 'bg-gray-300'
              }`}
            >
              <span className={`absolute top-0.5 left-0.5 w-6 h-6 bg-white rounded-full shadow transition-transform duration-200 ${
                config.enabled ? 'translate-x-7' : 'translate-x-0'
              }`} />
            </button>
          </div>
        </div>

        {/* Delivery bar */}
        {config.enabled && (
          <div className="mt-5 pt-5 border-t border-gray-100">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-bold text-gray-600 uppercase tracking-wider">Delivery Health</p>
              <p className="text-xs font-bold text-gray-700">{deliveryRate}%</p>
            </div>
            <div className="h-2.5 bg-gray-100 rounded-full overflow-hidden border border-gray-200">
              <div
                className="h-full bg-gray-900 rounded-full transition-all duration-1000"
                style={{ width: `${deliveryRate}%` }}
              />
            </div>
            <div className="flex justify-between mt-1.5">
              <p className="text-xs text-gray-400">0%</p>
              <p className="text-xs text-gray-400">100%</p>
            </div>
          </div>
        )}
      </div>

      {/* Add Recipient */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <div className="flex items-center gap-3 mb-5">
          <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center text-xl">
            ➕
          </div>
          <div>
            <h3 className="font-bold text-gray-900">Add Recipient</h3>
            <p className="text-xs text-gray-500 mt-0.5">Add email addresses to receive anomaly alerts</p>
          </div>
        </div>
        <form onSubmit={addRecipient} className="flex gap-3 flex-wrap">
          <div className="flex-1 min-w-60">
            <input
              type="email"
              placeholder="email@example.com"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900 focus:border-gray-900"
              required
            />
          </div>
          <button
            type="submit"
            className="bg-gray-900 text-white rounded-xl px-6 py-2.5 hover:bg-black transition-colors font-bold text-sm whitespace-nowrap"
          >
            + Add Recipient
          </button>
        </form>
      </div>

      {/* Recipients List */}
      <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100 bg-gray-50 flex items-center justify-between flex-wrap gap-3">
          <div>
            <h3 className="font-bold text-gray-900">
              Recipients <span className="text-gray-900 font-extrabold">({recipientCount})</span>
            </h3>
            <p className="text-xs text-gray-500 mt-0.5">These addresses receive anomaly alert emails</p>
          </div>
          {recipientCount > 0 && (
            <button
              onClick={sendTestEmail}
              disabled={sendingTest || !config.enabled}
              className={`text-sm font-bold px-4 py-2 rounded-xl transition-all ${
                sendingTest || !config.enabled
                  ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                  : 'bg-gray-900 text-white hover:bg-black'
              }`}
            >
              {sendingTest ? '⟳ Sending…' : '📤 Send Test Email'}
            </button>
          )}
        </div>

        {recipientCount === 0 ? (
          <div className="p-12 text-center">
            <p className="text-4xl mb-3">📭</p>
            <p className="text-gray-500 font-semibold text-lg">No recipients configured</p>
            <p className="text-sm text-gray-400 mt-1">Add an email address above to start receiving alerts</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {config.recipients.map((email, index) => (
              <div key={index} className="px-6 py-4 hover:bg-gray-50 transition-colors">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center text-lg flex-shrink-0">
                      📧
                    </div>
                    <div>
                      <p className="font-semibold text-gray-900">{email}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className={`w-1.5 h-1.5 rounded-full ${config.enabled ? 'bg-green-400 animate-pulse' : 'bg-gray-300'}`} />
                        <p className="text-xs text-gray-500">
                          {config.enabled ? 'Active — receiving alerts' : 'Inactive — alerts disabled'}
                        </p>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <span className={`text-xs font-bold px-2.5 py-1 rounded-full border ${
                      config.enabled
                        ? 'bg-black text-white border-black'
                        : 'bg-gray-100 text-gray-600 border-gray-200'
                    }`}>
                      {config.enabled ? 'ACTIVE' : 'PAUSED'}
                    </span>
                    <button
                      onClick={() => deleteRecipient(email)}
                      className="text-xs font-bold text-red-500 hover:text-red-700 px-3 py-1.5 rounded-xl hover:bg-red-50 border border-transparent hover:border-red-200 transition-all"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Activity Log */}
      {activityLog.length > 0 && (
        <div className="bg-white rounded-2xl border border-gray-200 p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-bold text-gray-900">Recent Activity</h3>
            <span className="text-xs font-bold bg-black text-white px-2.5 py-1 rounded-full">
              This session
            </span>
          </div>
          <div className="space-y-2">
            {activityLog.map((entry, i) => (
              <div key={i} className="flex items-center gap-3 p-3 rounded-xl bg-gray-50 border border-gray-100">
                <span className="text-lg flex-shrink-0">{entry.icon}</span>
                <p className="text-sm text-gray-700 flex-1">{entry.text}</p>
                <span className="text-xs text-gray-400 font-mono flex-shrink-0">{entry.ts}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Alert Coverage Info */}
      <div className="bg-white rounded-2xl border border-gray-200 p-5">
        <h3 className="font-bold text-gray-900 mb-4">Alert Coverage</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <CoverageCard
            icon="🔴"
            label="Critical Anomalies"
            description="Immediate alert sent to all recipients"
            active={config.enabled}
          />
          <CoverageCard
            icon="🟠"
            label="High Severity"
            description="Alert sent within the next batch window"
            active={config.enabled}
          />
          <CoverageCard
            icon="🟡"
            label="Medium & Low"
            description="Bundled in daily digest email"
            active={false}
          />
        </div>
      </div>
    </div>
  );
}

function KpiChip({ label, value, ok }) {
  return (
    <div className="bg-white/15 border border-white/20 rounded-xl px-3 py-2 text-center">
      <p className="text-gray-400 text-xs uppercase tracking-wide">{label}</p>
      <p className={`font-extrabold text-lg mt-0.5 ${ok === false ? 'text-yellow-300' : 'text-white'}`}>
        {value}
      </p>
    </div>
  );
}

function StatCard({ icon, label, value, ok, small }) {
  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-4 hover:shadow-md transition-shadow">
      <div className="flex items-center gap-3">
        <span className="text-2xl">{icon}</span>
        <div>
          <p className="text-xs text-gray-500">{label}</p>
          <p className={`font-extrabold mt-0.5 ${
            ok === true ? 'text-green-600' :
            ok === false ? 'text-gray-400' :
            'text-gray-900'
          } ${small ? 'text-base' : 'text-2xl'}`}>
            {value}
          </p>
        </div>
      </div>
    </div>
  );
}

function CoverageCard({ icon, label, description, active }) {
  return (
    <div className={`rounded-xl p-4 border-2 ${
      active ? 'border-gray-900 bg-gray-50' : 'border-gray-200 bg-white'
    }`}>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xl">{icon}</span>
        <span className={`text-xs font-extrabold px-2 py-0.5 rounded-full ${
          active ? 'bg-black text-white' : 'bg-gray-200 text-gray-500'
        }`}>
          {active ? 'ACTIVE' : 'INACTIVE'}
        </span>
      </div>
      <p className="font-bold text-gray-900 text-sm">{label}</p>
      <p className="text-xs text-gray-500 mt-1">{description}</p>
    </div>
  );
}

