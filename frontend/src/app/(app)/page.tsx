"use client";

import { useEffect, useState, useRef } from "react";
import { fetchAPI, WS_URL } from "@/lib/api";
import { MarkdownRenderer } from "@/components/MarkdownRenderer";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { useToast } from "@/components/Toast";
import { 
  GitFork, 
  Activity, 
  AlertOctagon, 
  Terminal, 
  Sparkles,
  RefreshCw,
  Box,
  Cpu,
  Layers
} from "lucide-react";

interface Repo {
  id: string;
  type: "github" | "gitlab" | "jenkins" | "azure";
  name: string;
}

interface AlertEvent {
  event: "failure" | "analysis_chunk";
  platform: string;
  repo: string;
  id: string;
  title?: string;
  trigger?: string;
  chunk?: string;
}

interface FailureAlert {
  id: string;
  repo: string;
  platform: string;
  title: string;
  trigger: string;
  timestamp: string; // ISO String
  analysis: string;
}

// Relative time formatter helper
function getRelativeTime(isoString: string) {
  const diff = Date.now() - new Date(isoString).getTime();
  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);

  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  return new Date(isoString).toLocaleDateString();
}

// Simple counter animation component
const AnimatedCounter = ({ value }: { value: number | string }) => {
  const [displayValue, setDisplayValue] = useState(0);
  const numValue = typeof value === 'string' ? parseInt(value, 10) : value;

  useEffect(() => {
    if (isNaN(numValue)) return;
    
    let startTimestamp: number;
    const duration = 1000;
    
    const step = (timestamp: number) => {
      if (!startTimestamp) startTimestamp = timestamp;
      const progress = Math.min((timestamp - startTimestamp) / duration, 1);
      setDisplayValue(Math.floor(progress * numValue));
      if (progress < 1) {
        window.requestAnimationFrame(step);
      } else {
        setDisplayValue(numValue);
      }
    };
    
    window.requestAnimationFrame(step);
  }, [numValue]);

  return <span>{isNaN(numValue) ? value : displayValue}</span>;
};

export default function DashboardPage() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loading, setLoading] = useState(true);
  const [alerts, setAlerts] = useState<FailureAlert[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [selectedAlert, setSelectedAlert] = useState<FailureAlert | null>(null);
  const [reconnecting, setReconnecting] = useState(false);
  const [activeModel, setActiveModel] = useState("Gemini 1.5 Pro");

  const { toast } = useToast();
  const wsRef = useRef<WebSocket | null>(null);

  const loadDashboard = async () => {
    setLoading(true);
    try {
      const [data, cfg] = await Promise.all([
        fetchAPI("/api/repos"),
        fetchAPI("/api/config").catch(() => null)
      ]);
      setRepos(data);
      if (cfg && cfg.google_model) {
        const modelNames: Record<string, string> = {
          "gemini-1.5-pro": "Gemini 1.5 Pro",
          "gemini-1.5-flash": "Gemini 1.5 Flash",
          "gemini-2.0-flash-exp": "Gemini 2.0 Flash Exp",
          "gemini-2.5-flash": "Gemini 2.5 Flash",
          "gemini-2.5-pro": "Gemini 2.5 Pro"
        };
        const name = modelNames[cfg.google_model] || cfg.google_model.split("-").map((word: string) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
        setActiveModel(name);
      }
    } catch (err) {
      toast("Failed to load dashboard data. Check backend status.", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboard();
  }, []);

  // Connect to live monitor WebSocket with Reconnect logic
  useEffect(() => {
    let ws: WebSocket;
    let reconnectTimeout: NodeJS.Timeout;
    let reconnectAttempts = 0;

    const connect = () => {
      if (wsRef.current?.readyState === WebSocket.OPEN) return;
      
      setReconnecting(true);
      ws = new WebSocket(`${WS_URL}/ws/monitors`);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsConnected(true);
        setReconnecting(false);
        reconnectAttempts = 0;
        toast("Connected to live failure feed", "success");
      };

      ws.onmessage = (event) => {
        try {
          const data: AlertEvent = JSON.parse(event.data);
          
          if (data.event === "failure") {
            const newAlert: FailureAlert = {
              id: data.id,
              repo: data.repo,
              platform: data.platform,
              title: data.title || "Failure Event",
              trigger: data.trigger || "unknown",
              timestamp: new Date().toISOString(),
              analysis: ""
            };
            setAlerts((prev) => [newAlert, ...prev]);
            setSelectedAlert(newAlert);
            toast(`New build failure detected in ${data.repo}`, "warning");
          } else if (data.event === "analysis_chunk") {
            setAlerts((prev) => 
              prev.map((alert) => {
                if (alert.repo === data.repo && alert.id === data.id) {
                  const updated = {
                    ...alert,
                    analysis: alert.analysis + (data.chunk || "")
                  };
                  // Update current selected alert if it matches
                  setSelectedAlert((currSelected) => {
                    if (currSelected && currSelected.repo === data.repo && currSelected.id === data.id) {
                      return updated;
                    }
                    return currSelected;
                  });
                  return updated;
                }
                return alert;
              })
            );
          }
        } catch (err) {
          console.error("Failed to parse monitor event:", err);
        }
      };

      ws.onclose = () => {
        setWsConnected(false);
        setReconnecting(false);
        
        // Exponential backoff reconnect
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
        reconnectAttempts++;
        reconnectTimeout = setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      if (ws) ws.close();
      clearTimeout(reconnectTimeout);
    };
  }, [toast]);

  return (
    <div className="space-y-8 animate-fade-slide-up pb-12">
      {/* Banner */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 border border-slate-700 shadow-xl">
        <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-20 mix-blend-overlay pointer-events-none"></div>
        <div className="absolute top-0 right-0 w-64 h-64 bg-teal-500/10 blur-[80px] rounded-full pointer-events-none transform translate-x-1/2 -translate-y-1/2"></div>
        
        <div className="p-8 relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="p-2 bg-white/10 rounded-lg backdrop-blur-sm border border-white/10">
                <Activity className="h-5 w-5 text-teal-400" />
              </div>
              <h2 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
                DevOps Diagnostic Center
              </h2>
            </div>
            <p className="text-slate-400 text-sm leading-relaxed max-w-2xl">
              Automatic background polling of pipeline failure logs and Gemini diagnostic streaming.
            </p>
          </div>
          
          <div className="flex items-center gap-3 shrink-0 bg-slate-950/50 backdrop-blur-md border border-white/10 rounded-full px-4 py-2 shadow-inner">
            {reconnecting && (
              <span className="text-xs text-slate-400 flex items-center gap-2 animate-pulse font-medium">
                <RefreshCw className="h-3 w-3 animate-spin text-teal-500" />
                Reconnecting...
              </span>
            )}
            {!reconnecting && (
              <div className="relative flex items-center justify-center h-3 w-3">
                {wsConnected && (
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                )}
                <span className={`relative inline-flex rounded-full h-2 w-2 ${wsConnected ? "bg-emerald-500" : "bg-rose-500"}`}></span>
              </div>
            )}
            <span className={`text-xs font-bold ${wsConnected ? 'text-emerald-400' : 'text-rose-400'}`}>
              {wsConnected ? "Monitor Active" : "Offline / Connecting"}
            </span>
          </div>
        </div>
      </div>

      {/* KPI Stats Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="glass-card p-6 rounded-2xl flex flex-col justify-between relative overflow-hidden group hover:-translate-y-1 transition-all duration-300 border-t-4 border-t-teal-500">
          <div className="absolute -right-4 -top-4 opacity-5 group-hover:scale-110 transition-transform duration-500">
            <GitFork className="w-32 h-32" />
          </div>
          <div className="flex justify-between items-start mb-4 relative z-10">
            <span className="text-slate-500 text-[10px] font-bold uppercase tracking-widest bg-slate-100 px-2.5 py-1 rounded-full">Total Repos</span>
            <div className="p-2 bg-teal-50 text-teal-600 rounded-xl shadow-sm border border-teal-100/50">
              <Layers className="h-4.5 w-4.5" />
            </div>
          </div>
          <span className="text-4xl font-black text-slate-800 tracking-tight relative z-10">
            <AnimatedCounter value={repos.length} />
          </span>
        </div>

        <div className="glass-card p-6 rounded-2xl flex flex-col justify-between relative overflow-hidden group hover:-translate-y-1 transition-all duration-300 border-t-4 border-t-emerald-500">
          <div className="absolute -right-4 -top-4 opacity-5 group-hover:scale-110 transition-transform duration-500">
            <Activity className="w-32 h-32" />
          </div>
          <div className="flex justify-between items-start mb-4 relative z-10">
            <span className="text-slate-500 text-[10px] font-bold uppercase tracking-widest bg-slate-100 px-2.5 py-1 rounded-full">Active Monitors</span>
            <div className="p-2 bg-emerald-50 text-emerald-600 rounded-xl shadow-sm border border-emerald-100/50">
              <Activity className="h-4.5 w-4.5" />
            </div>
          </div>
          <span className="text-4xl font-black text-slate-800 tracking-tight relative z-10">
            <AnimatedCounter value={wsConnected && repos.length > 0 ? repos.length : 0} />
          </span>
        </div>

        <div className="glass-card p-6 rounded-2xl flex flex-col justify-between relative overflow-hidden group hover:-translate-y-1 transition-all duration-300 border-t-4 border-t-rose-500">
          <div className="absolute -right-4 -top-4 opacity-5 group-hover:scale-110 transition-transform duration-500">
            <AlertOctagon className="w-32 h-32" />
          </div>
          <div className="flex justify-between items-start mb-4 relative z-10">
            <span className="text-slate-500 text-[10px] font-bold uppercase tracking-widest bg-slate-100 px-2.5 py-1 rounded-full">Failures</span>
            <div className="p-2 bg-rose-50 text-rose-600 rounded-xl shadow-sm border border-rose-100/50">
              <AlertOctagon className="h-4.5 w-4.5" />
            </div>
          </div>
          <span className="text-4xl font-black text-slate-800 tracking-tight relative z-10">
            <AnimatedCounter value={alerts.length} />
          </span>
        </div>

        <div className="glass-card p-6 rounded-2xl flex flex-col justify-between relative overflow-hidden group hover:-translate-y-1 transition-all duration-300 border-t-4 border-t-indigo-500">
          <div className="absolute -right-4 -top-4 opacity-5 group-hover:scale-110 transition-transform duration-500">
            <Sparkles className="w-32 h-32" />
          </div>
          <div className="flex justify-between items-start mb-4 relative z-10">
            <span className="text-slate-500 text-[10px] font-bold uppercase tracking-widest bg-slate-100 px-2.5 py-1 rounded-full">AI Engine</span>
            <div className="p-2 bg-indigo-50 text-indigo-600 rounded-xl shadow-sm border border-indigo-100/50">
              <Cpu className="h-4.5 w-4.5" />
            </div>
          </div>
          <div className="relative z-10">
            <span className="text-sm font-bold text-transparent bg-clip-text bg-gradient-to-r from-indigo-600 to-purple-600 block bg-slate-100 border border-slate-200/60 px-3 py-1.5 rounded-xl shadow-sm w-max">
              {activeModel}
            </span>
          </div>
        </div>
      </div>

      {/* Grid: Overview cards & Monitor list */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-8">
        
        {/* Left: Stats & Monitored Repos */}
        <div className="xl:col-span-1 space-y-8 flex flex-col h-full">
          
          {/* Monitored Repos Panel */}
          <div className="glass-card rounded-2xl p-6 flex flex-col flex-1 min-h-[300px]">
            <h3 className="font-extrabold text-slate-800 text-sm border-b border-slate-200/60 pb-4 mb-4 flex justify-between items-center">
              <div className="flex items-center gap-2">
                <Box className="h-4 w-4 text-teal-600" />
                Monitored Items
              </div>
              <span className="text-[10px] font-bold text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">Active Poller</span>
            </h3>
            
            <div className="flex-1 overflow-y-auto pr-2 -mr-2">
              {loading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map((n) => (
                    <div key={n} className="h-14 bg-slate-100/50 rounded-xl animate-shimmer" />
                  ))}
                </div>
              ) : repos.length === 0 ? (
                <div className="py-6 h-full flex items-center justify-center">
                  <EmptyState
                    title="No repos setup"
                    description="Setup a GitHub, GitLab, Jenkins or Azure DevOps repo to start monitoring."
                    actionLabel="Add Repository"
                    onAction={() => window.location.href = "/repos"}
                  />
                </div>
              ) : (
                <div className="space-y-3">
                  {repos.map((repo) => (
                    <div key={repo.id} className="group flex justify-between items-center p-3.5 bg-white border border-slate-200/80 rounded-xl hover:border-teal-300 hover:shadow-[0_4px_12px_-4px_rgba(45,212,191,0.2)] transition-all duration-200">
                      <div className="min-w-0 pr-3">
                        <p className="font-bold text-slate-800 text-sm truncate group-hover:text-teal-700 transition-colors" title={repo.name}>
                          {repo.name}
                        </p>
                        <div className="mt-1.5 opacity-80 group-hover:opacity-100 transition-opacity">
                          <StatusBadge type="platform" value={repo.type} />
                        </div>
                      </div>
                      <div className="relative flex h-2.5 w-2.5 shrink-0" title="Monitoring active">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Failure Alert Feed */}
          <div className="glass-card rounded-2xl p-6 flex flex-col flex-1 min-h-[300px]">
            <h3 className="font-extrabold text-slate-800 text-sm border-b border-slate-200/60 pb-4 mb-4 flex items-center gap-2">
              <AlertOctagon className="h-4 w-4 text-rose-500" />
              Live Feed Alerts
            </h3>
            
            <div className="flex-1 overflow-y-auto pr-2 -mr-2">
              {alerts.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center text-slate-400 py-10">
                  <div className="p-4 bg-slate-100 rounded-full mb-3 shadow-inner border border-slate-200/50">
                    <Terminal className="h-6 w-6 text-slate-300" />
                  </div>
                  <p className="text-xs font-medium">No failures detected in this session.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {alerts.map((alert, idx) => (
                    <button
                      key={idx}
                      onClick={() => setSelectedAlert(alert)}
                      className={`w-full text-left p-4 rounded-xl transition-all duration-300 flex flex-col gap-3 relative overflow-hidden ${
                        selectedAlert?.repo === alert.repo && selectedAlert?.id === alert.id
                          ? "bg-gradient-to-r from-rose-50 to-white border-l-4 border-l-rose-500 border border-slate-200 shadow-md transform scale-[1.02] z-10"
                          : "bg-white border-l-4 border-l-transparent border border-slate-200 hover:bg-slate-50 hover:border-slate-300 hover:shadow-sm"
                      }`}
                      style={{ animation: 'slideInRight 0.3s ease-out forwards', animationDelay: `${Math.min(idx * 0.05, 0.5)}s`, opacity: 0 }}
                    >
                      <div className="flex justify-between items-center w-full">
                        <StatusBadge type="platform" value={alert.platform} />
                        <span className="text-[10px] font-bold text-slate-400 bg-slate-100 px-2 py-0.5 rounded-md border border-slate-200/50">{getRelativeTime(alert.timestamp)}</span>
                      </div>
                      <div>
                        <p className="font-extrabold text-slate-800 text-sm truncate w-full">{alert.repo}</p>
                        <p className="text-slate-500 font-medium text-[11px] truncate w-full mt-1 bg-slate-50 px-2 py-1 rounded-md border border-slate-100">{alert.title}</p>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right: Live AI Failure Diagnostic Panel */}
        <div className="xl:col-span-2 h-full">
          <div className="glass-panel-dark rounded-2xl shadow-2xl h-full flex flex-col min-h-[650px] border border-slate-800 relative overflow-hidden">
            {/* Terminal Top Bar */}
            <div className="px-6 py-4 border-b border-slate-800 flex justify-between items-center bg-slate-950/80 rounded-t-2xl relative z-10">
              <div className="flex items-center gap-4">
                <div className="flex gap-1.5">
                  <div className="h-3 w-3 rounded-full bg-rose-500 border border-rose-600"></div>
                  <div className="h-3 w-3 rounded-full bg-amber-500 border border-amber-600"></div>
                  <div className="h-3 w-3 rounded-full bg-emerald-500 border border-emerald-600"></div>
                </div>
                <div>
                  <h3 className="font-bold text-slate-200 text-sm flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-teal-400" />
                    AI Root Cause Analysis
                  </h3>
                </div>
              </div>
              {selectedAlert && (
                <span className="text-[10px] font-bold text-teal-300 bg-teal-500/10 px-3 py-1 rounded-full border border-teal-500/20 shadow-[0_0_10px_rgba(45,212,191,0.1)]">
                  ID: {selectedAlert.id.substring(0,8)}...
                </span>
              )}
            </div>

            <div className="flex-1 p-6 overflow-y-auto space-y-6 relative z-10 bg-slate-900/50">
              {!selectedAlert ? (
                <div className="h-full flex flex-col items-center justify-center text-center text-slate-400 max-w-sm mx-auto py-12">
                  <div className="relative mb-6">
                    <div className="absolute inset-0 bg-teal-500 blur-xl opacity-20 rounded-full animate-pulse-ring"></div>
                    <div className="p-5 bg-slate-800/80 border border-slate-700 rounded-2xl relative z-10 shadow-2xl">
                      <Sparkles className="h-10 w-10 text-teal-400" />
                    </div>
                  </div>
                  <h4 className="font-bold text-slate-300 text-base">Waiting for failure event...</h4>
                  <p className="text-slate-500 text-sm mt-2.5 leading-relaxed">
                    When an active repository build fails, the alert feed will capture the event and stream root cause diagnostics here automatically.
                  </p>
                </div>
              ) : (
                <div className="space-y-6 animate-fade-slide-up">
                  {/* Alert metadata context pills */}
                  <div className="flex flex-wrap gap-3">
                    <div className="flex items-center gap-2 bg-slate-800/80 border border-slate-700 px-3 py-2 rounded-xl shadow-inner">
                      <span className="text-slate-500 text-[10px] font-bold uppercase tracking-widest">Platform</span>
                      <StatusBadge type="platform" value={selectedAlert.platform} />
                    </div>
                    <div className="flex items-center gap-2 bg-slate-800/80 border border-slate-700 px-3 py-2 rounded-xl shadow-inner">
                      <span className="text-slate-500 text-[10px] font-bold uppercase tracking-widest">Repo</span>
                      <span className="font-bold text-slate-200 text-sm truncate max-w-[200px]" title={selectedAlert.repo}>{selectedAlert.repo}</span>
                    </div>
                    <div className="flex items-center gap-2 bg-slate-800/80 border border-slate-700 px-3 py-2 rounded-xl shadow-inner">
                      <span className="text-slate-500 text-[10px] font-bold uppercase tracking-widest">Trigger</span>
                      <span className="font-bold text-slate-200 text-sm capitalize bg-slate-700/50 px-2 py-0.5 rounded-lg">{selectedAlert.trigger}</span>
                    </div>
                  </div>

                  <div className="w-full bg-slate-800/50 border border-slate-700/50 rounded-xl px-4 py-3 shadow-inner">
                    <span className="text-slate-500 text-[10px] font-bold uppercase tracking-widest block mb-1">Job / Build Context</span>
                    <span className="font-mono text-slate-300 text-sm truncate block" title={selectedAlert.title}>{selectedAlert.title}</span>
                  </div>

                  {/* AI streamed output formatting */}
                  <div className="bg-slate-950 border border-slate-800 rounded-xl shadow-2xl p-6 min-h-[300px] font-sans">
                    {selectedAlert.analysis ? (
                      <div className={selectedAlert.analysis.endsWith("...") || selectedAlert.analysis.length < 50 ? "streaming-cursor" : ""}>
                        <MarkdownRenderer 
                          content={selectedAlert.analysis} 
                          isStreaming={false} 
                        />
                      </div>
                    ) : (
                      <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-4 py-16">
                        <div className="relative">
                          <div className="absolute inset-0 bg-teal-500 blur-md opacity-30 rounded-full animate-ping"></div>
                          <RefreshCw className="h-8 w-8 text-teal-400 animate-spin relative z-10" />
                        </div>
                        <span className="text-sm font-bold text-teal-400 tracking-wide animate-pulse">
                          Gemini is fetching logs and analyzing failure...
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
