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
              <div className="flex h-screen bg-gray-50">
                {/* Left Sidebar */}
                <aside className="w-64 bg-zinc-950 text-white flex flex-col border-r border-zinc-800">
                  {/* Brand */}
                  <div className="px-5 py-6 border-b border-zinc-800">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-white rounded-xl flex items-center justify-center shadow-lg">
                        <span className="text-xl">🤖</span>
                      </div>
                      <div className="leading-tight">
                        <h1 className="text-base font-bold tracking-tight">AI DevOps</h1>
                        <p className="text-[10px] text-zinc-400 font-bold uppercase tracking-widest">Monitor · Pro</p>
                      </div>
                    </div>
                  </div>

                  {/* Nav */}
                  <nav className="flex-1 p-4 space-y-7 overflow-y-auto">
                    <div>
                      <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-[0.2em] mb-4 px-3">
                        Monitoring
                      </h3>
                      <ul className="space-y-1.5">
                        {navItems.map((item) => (
                          <li key={item.path}>
                            <NavLink
                              to={item.path}
                              end={item.path === "/"}
                              className={({ isActive }) =>
                                `flex items-center gap-3 px-4 py-2.5 rounded-xl transition-all duration-200 border ${
                                  isActive 
                                    ? "bg-white text-zinc-950 shadow-[0_4px_12px_rgba(255,255,255,0.1)] border-white" 
                                    : "text-zinc-400 hover:text-white hover:bg-zinc-900 border-transparent"
                                }`
                              }
                            >
                              <span className="text-lg">{item.icon}</span>
                              <span className="text-sm font-bold">{item.name}</span>
                            </NavLink>
                          </li>
                        ))}
                      </ul>
                    </div>

                    <div>
                      <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-[0.2em] mb-4 px-3">
                        Settings
                      </h3>
                      <ul className="space-y-1.5">
                        {settingsItems.map((item) => (
                          <li key={item.path}>
                            <NavLink
                              to={item.path}
                              className={({ isActive }) =>
                                `flex items-center gap-3 px-4 py-2.5 rounded-xl transition-all duration-200 border ${
                                  isActive 
                                    ? "bg-white text-zinc-950 shadow-[0_4px_12px_rgba(255,255,255,0.1)] border-white" 
                                    : "text-zinc-400 hover:text-white hover:bg-zinc-900 border-transparent"
                                }`
                              }
                            >
                              <span className="text-lg">{item.icon}</span>
                              <span className="text-sm font-bold">{item.name}</span>
                            </NavLink>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </nav>

                  {/* User Profile */}
                  {isAuthenticated && user && (
                    <div className="p-4 bg-zinc-950 border-t border-zinc-900">
                      <div className="bg-zinc-900/50 rounded-2xl p-4 border border-zinc-800">
                        <div className="flex items-center gap-3 mb-4">
                          <div className="w-10 h-10 bg-gradient-to-br from-zinc-700 to-zinc-900 rounded-full flex items-center justify-center text-white font-bold border border-zinc-700 shadow-inner">
                            {user.username?.[0]?.toUpperCase() || 'U'}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-bold text-white truncate">
                              {user.username}
                            </p>
                            <p className="text-[10px] text-zinc-500 truncate">
                              {user.email}
                            </p>
                          </div>
                        </div>
                        <button
                          onClick={logout}
                          className="w-full bg-white hover:bg-zinc-100 text-zinc-950 text-xs font-bold py-2.5 px-4 rounded-xl transition-all duration-200 shadow-sm"
                        >
                          Sign Out
                        </button>
                      </div>
                    </div>
                  )}
                </aside>

                {/* Main Content */}
                <main className="flex-1 overflow-y-auto bg-gray-50">
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

