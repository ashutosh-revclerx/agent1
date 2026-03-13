import { BrowserRouter as Router, Routes, Route, NavLink } from "react-router-dom";
import "./index.css";

import { AuthProvider, useAuth } from "./contexts/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import Login from "./components/Login";
import Register from "./components/Register";
import Dashboard from "./components/Dashboard";
import Anomalies from "./components/Anomalies";
import RCAResults from "./components/RCAResults";
import EmailSettings from "./components/EmailSettings";
import ServerSettings from "./components/ServerSettings";
import MetricsOverview from "./components/MetricsOverview";
import LangfuseMonitor from "./components/LangfuseMonitor";
import AIAnalyst from "./components/AIAnalyst";

function AppContent() {
  const { user, logout, isAuthenticated } = useAuth();

  const navItems = [
    { path: "/", name: "Dashboard", icon: "📊" },
    { path: "/metrics", name: "Metrics", icon: "📈" },
    { path: "/anomalies", name: "Anomalies", icon: "🚨" },
    { path: "/rca", name: "RCA Results", icon: "🔍" },
    { path: "/langfuse", name: "LLM Monitor", icon: "🤖" },
    { path: "/chat", name: "AI Analyst", icon: "🧠" },
  ];

  const settingsItems = [
    { path: "/settings/servers", name: "Alerts & Servers", icon: "⚙️" },
    { path: "/settings/email", name: "Email Config", icon: "📧" },
  ];

  const linkBase =
    "flex items-center gap-3 px-4 py-2.5 rounded-lg transition-colors";
  const linkInactive =
    "text-blue-100 hover:bg-blue-50/10 hover:text-white";
  const linkActive =
    "bg-white text-blue-700 shadow-sm";

  return (
    <Router>
      <Routes>
        {/* Public Routes */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        {/* Protected Routes */}
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <div className="flex h-screen bg-blue-50">
                {/* Left Sidebar */}
                <aside className="w-64 bg-blue-600 text-white flex flex-col border-r border-blue-500/40">
                  {/* Brand */}
                  <div className="px-5 py-5 border-b border-blue-500/40">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 bg-white rounded-lg flex items-center justify-center">
                        <span className="text-xl">🤖</span>
                      </div>
                      <div className="leading-tight">
                        <h1 className="text-base font-bold">AI DevOps</h1>
                        <p className="text-xs text-blue-200">Monitoring</p>
                      </div>
                    </div>
                  </div>

                  {/* Nav */}
                  <nav className="flex-1 p-4 space-y-6 overflow-y-auto">
                    <div>
                      <h3 className="text-[11px] font-semibold text-blue-200 uppercase tracking-wider mb-2 px-2">
                        Monitoring
                      </h3>
                      <ul className="space-y-2">
                        {navItems.map((item) => (
                          <li key={item.path}>
                            <NavLink
                              to={item.path}
                              end={item.path === "/"}
                              className={({ isActive }) =>
                                `${linkBase} ${isActive ? linkActive : linkInactive}`
                              }
                            >
                              <span className="text-lg">{item.icon}</span>
                              <span className="text-sm font-semibold">{item.name}</span>
                            </NavLink>
                          </li>
                        ))}
                      </ul>
                    </div>

                    <div>
                      <h3 className="text-[11px] font-semibold text-blue-200 uppercase tracking-wider mb-2 px-2">
                        Settings
                      </h3>
                      <ul className="space-y-2">
                        {settingsItems.map((item) => (
                          <li key={item.path}>
                            <NavLink
                              to={item.path}
                              className={({ isActive }) =>
                                `${linkBase} ${isActive ? linkActive : linkInactive}`
                              }
                            >
                              <span className="text-lg">{item.icon}</span>
                              <span className="text-sm font-semibold">{item.name}</span>
                            </NavLink>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </nav>

                  {/* User Profile */}
                  {isAuthenticated && user && (
                    <div className="p-4 border-t border-blue-500/40">
                      <div className="bg-blue-700/50 rounded-lg p-3">
                        <div className="flex items-center gap-3 mb-3">
                          <div className="w-10 h-10 bg-blue-500 rounded-full flex items-center justify-center text-white font-bold">
                            {user.username?.[0]?.toUpperCase() || 'U'}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-semibold text-white truncate">
                              {user.username}
                            </p>
                            <p className="text-xs text-blue-200 truncate">
                              {user.email}
                            </p>
                          </div>
                        </div>
                        <button
                          onClick={logout}
                          className="w-full bg-blue-800 hover:bg-blue-900 text-white text-sm font-semibold py-2 px-3 rounded-lg transition-colors"
                        >
                          Sign Out
                        </button>
                      </div>
                    </div>
                  )}
                </aside>

                {/* Main Content */}
                <main className="flex-1 overflow-y-auto bg-blue-50">
                  <div className="p-6 md:p-8">
                    <Routes>
                      <Route path="/" element={<Dashboard />} />
                      <Route path="/metrics" element={<MetricsOverview />} />
                      <Route path="/anomalies" element={<Anomalies />} />
                      <Route path="/rca" element={<RCAResults />} />
                      <Route path="/settings/servers" element={<ServerSettings />} />
                      <Route path="/settings/email" element={<EmailSettings />} />
                      <Route path="/langfuse" element={<LangfuseMonitor />} />
                      <Route path="/chat" element={<AIAnalyst />} />
                    </Routes>
                  </div>
                </main>
              </div>
            </ProtectedRoute>
          }
        />
      </Routes>
    </Router>
  );
}

function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

export default App;

