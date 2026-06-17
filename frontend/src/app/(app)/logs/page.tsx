"use client";

import { useEffect, useState, useRef } from "react";
import { fetchAPI, WS_URL } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { useToast } from "@/components/Toast";
import { 
  Download, 
  Terminal, 
  Trash2, 
  Copy, 
  Check, 
  Filter, 
  ChevronLeft, 
  ChevronRight,
  ShieldCheck
} from "lucide-react";

interface LogEntry {
  ts: number;
  tool: string;
  allowed: boolean;
  reason: string;
  arg_keys: string[];
}

export default function LogsPage() {
  const [activeTab, setActiveTab] = useState<"history" | "live">("history");
  
  // Historical Log states
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalLogs, setTotalLogs] = useState(0);
  
  // Filters
  const [toolFilter, setToolFilter] = useState("");
  const [allowedFilter, setAllowedFilter] = useState<string>("all");
  const [reasonFilter, setReasonFilter] = useState("");

  // Live stream states
  const [liveLogs, setLiveLogs] = useState<LogEntry[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  const { toast } = useToast();
  const liveLogsEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const perPage = 25;

  const loadLogs = async () => {
    setLoading(true);
    let query = `/api/logs?page=${page}&per_page=${perPage}`;
    if (toolFilter) query += `&tool=${toolFilter}`;
    if (allowedFilter !== "all") query += `&allowed=${allowedFilter === "true"}`;
    if (reasonFilter) query += `&reason=${reasonFilter}`;

    try {
      const data = await fetchAPI(query);
      setLogs(data.logs);
      setTotalLogs(data.total);
      setTotalPages(Math.ceil(data.total / perPage) || 1);
    } catch (err: any) {
      toast("Failed to load historical audit logs", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === "history") {
      loadLogs();
    }
  }, [page, toolFilter, allowedFilter, reasonFilter, activeTab]);

  // WebSocket Live Tail Connection
  useEffect(() => {
    if (activeTab === "live") {
      setLiveLogs([]);
      const ws = new WebSocket(`${WS_URL}/ws/logs`);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsConnected(true);
        toast("Connected to live audit trail", "success");
      };

      ws.onmessage = (event) => {
        try {
          const entry: LogEntry = JSON.parse(event.data);
          setLiveLogs((prev) => [...prev, entry].slice(-100)); // Keep last 100 entries
        } catch {
          // ignore parsing error
        }
      };

      ws.onclose = () => {
        setWsConnected(false);
      };

      return () => {
        ws.close();
      };
    }
  }, [activeTab]);

  // Scroll to bottom of live logs
  useEffect(() => {
    if (activeTab === "live" && liveLogsEndRef.current) {
      liveLogsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [liveLogs, activeTab]);

  const formatTime = (ts: number) => {
    if (!ts) return "-";
    const date = new Date(ts * 1000);
    return date.toLocaleTimeString() + " " + date.toLocaleDateString();
  };

  const handleCopyLogs = async (text: string, index: number) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedIndex(index);
      setTimeout(() => setCopiedIndex(null), 2000);
      toast("Log entry copied to clipboard", "success");
    } catch (err) {
      toast("Failed to copy log", "error");
    }
  };

  const handleClearLive = () => {
    setLiveLogs([]);
    toast("Live log monitor terminal cleared", "info");
  };

  return (
    <div className="space-y-6 animate-fade-slide-up">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center bg-white border border-slate-200 p-6 rounded-2xl gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800 tracking-tight flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-teal-600" />
            Security & Tool Audit Logs
          </h2>
          <p className="text-slate-500 text-xs mt-1 leading-relaxed">
            Verify LLM agent interactions, shell allowlists, and execution security sandboxes.
          </p>
        </div>
        
        <a
          href="http://localhost:8000/api/logs/download"
          download
          className="bg-white hover:bg-slate-50 text-slate-700 border border-slate-300 font-semibold text-xs px-4 py-2.5 rounded-xl shadow-xs transition duration-150 flex items-center gap-1.5 shrink-0"
        >
          <Download className="h-4 w-4" />
          Download Audit Logs
        </a>
      </div>

      {/* Tabs */}
      <div className="border-b border-slate-200 flex gap-6">
        <button
          onClick={() => setActiveTab("history")}
          className={`pb-3 font-semibold text-sm border-b-2 px-1 transition-all duration-150 ${
            activeTab === "history" 
              ? "border-teal-600 text-teal-600" 
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Search History
        </button>
        <button
          onClick={() => setActiveTab("live")}
          className={`pb-3 font-semibold text-sm border-b-2 px-1 transition-all duration-150 flex items-center gap-2 ${
            activeTab === "live" 
              ? "border-teal-600 text-teal-600" 
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Live Console Monitor
          <span className={`h-2 w-2 rounded-full ${wsConnected ? "bg-emerald-500 animate-pulse" : "bg-slate-300"}`}></span>
        </button>
      </div>

      {/* Tab: Search History */}
      {activeTab === "history" && (
        <div className="space-y-4">
          
          {/* Filters Bar */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 bg-white border border-slate-200 p-4 rounded-xl shadow-xs">
            <div>
              <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                <Filter className="h-3 w-3" /> Tool Name
              </label>
              <input
                type="text"
                placeholder="e.g. run_shell"
                value={toolFilter}
                onChange={(e) => { setToolFilter(e.target.value); setPage(1); }}
                className="w-full border border-slate-250 rounded-xl px-3 py-2 text-xs focus:outline-none focus:border-teal-500 bg-white"
              />
            </div>
            
            <div>
              <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">Sandbox State</label>
              <select
                value={allowedFilter}
                onChange={(e) => { setAllowedFilter(e.target.value); setPage(1); }}
                className="w-full border border-slate-250 rounded-xl px-3 py-2 text-xs focus:outline-none focus:border-teal-500 bg-white font-semibold"
              >
                <option value="all">All Logs</option>
                <option value="true">Allowed</option>
                <option value="false">Blocked / Disallowed</option>
              </select>
            </div>

            <div>
              <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">Execution Reason</label>
              <input
                type="text"
                placeholder="e.g. ok, allowlist_check_failed"
                value={reasonFilter}
                onChange={(e) => { setReasonFilter(e.target.value); setPage(1); }}
                className="w-full border border-slate-250 rounded-xl px-3 py-2 text-xs focus:outline-none focus:border-teal-500 bg-white"
              />
            </div>
          </div>

          {/* Logs Table */}
          <div className="bg-white border border-slate-200 rounded-2xl shadow-xs overflow-hidden">
            {loading ? (
              <div className="p-8 space-y-4">
                {[1, 2, 3].map((n) => (
                  <div key={n} className="h-12 bg-slate-50 border border-slate-100 rounded-xl animate-shimmer" />
                ))}
              </div>
            ) : logs.length === 0 ? (
              <div className="p-12 text-center text-slate-400 text-xs italic">
                No matching security audit logs found in storage.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-slate-55 border-b border-slate-200 text-slate-500 font-bold uppercase tracking-wider text-[10px]">
                      <th className="p-4">Time</th>
                      <th className="p-4">Tool</th>
                      <th className="p-4">Sandbox Check</th>
                      <th className="p-4">Decision Detail</th>
                      <th className="p-4">Params</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-150 text-slate-700">
                    {logs.map((entry, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/50 transition duration-100">
                        <td className="p-4 whitespace-nowrap text-slate-400 font-medium">{formatTime(entry.ts)}</td>
                        <td className="p-4 font-mono font-bold text-slate-800">{entry.tool}</td>
                        <td className="p-4">
                          <span className={`px-2 py-0.5 rounded-full font-bold text-[9px] uppercase border ${
                            entry.allowed 
                              ? "bg-emerald-50 text-emerald-700 border-emerald-200" 
                              : "bg-rose-50 text-rose-700 border-rose-200"
                          }`}>
                            {entry.allowed ? "Passed" : "Blocked"}
                          </span>
                        </td>
                        <td className="p-4 font-medium text-slate-600">{entry.reason}</td>
                        <td className="p-4 font-mono text-[10px] text-slate-400 max-w-xs truncate" title={entry.arg_keys ? entry.arg_keys.join(", ") : ""}>
                          {entry.arg_keys ? entry.arg_keys.join(", ") : "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Pagination footer */}
            <div className="px-6 py-4 border-t border-slate-100 flex items-center justify-between bg-slate-50/50">
              <span className="text-slate-400 text-xs font-semibold">
                Total Logs: <span className="text-slate-700 font-bold">{totalLogs}</span>
              </span>

              <div className="flex items-center gap-1">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
                  className="p-1.5 border border-slate-350 hover:bg-white rounded-lg text-slate-600 disabled:opacity-50 transition"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <span className="px-3 text-xs font-semibold text-slate-500">
                  {page} of {totalPages}
                </span>
                <button
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                  className="p-1.5 border border-slate-350 hover:bg-white rounded-lg text-slate-600 disabled:opacity-50 transition"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab: Live Stream */}
      {activeTab === "live" && (
        <div className="bg-slate-950 rounded-2xl shadow-xl border border-slate-800 overflow-hidden flex flex-col h-[500px]">
          {/* Status bar */}
          <div className="bg-slate-900/80 px-6 py-3 border-b border-slate-850 flex justify-between items-center shrink-0">
            <span className="text-[10px] font-bold text-slate-400 flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full ${wsConnected ? "bg-emerald-500 animate-pulse" : "bg-rose-500"}`}></span>
              {wsConnected ? "MONITOR TAIL ACTIVE" : "OFFLINE"}
            </span>
            <div className="flex gap-2">
              <button
                onClick={handleClearLive}
                className="text-[10px] text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 font-bold px-2 py-1 rounded-lg transition flex items-center gap-1"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Clear
              </button>
            </div>
          </div>

          {/* Terminal output */}
          <div className="flex-1 p-6 font-mono text-[11px] overflow-y-auto space-y-2.5 text-slate-300 bg-slate-950 select-text">
            {liveLogs.length === 0 ? (
              <p className="text-slate-500 italic h-full flex items-center justify-center">Waiting for security tool audits to trigger...</p>
            ) : (
              liveLogs.map((entry, idx) => {
                const logText = `${formatTime(entry.ts)} [${entry.allowed ? "OK" : "BLOCKED"}] ${entry.tool} (${entry.reason})`;
                return (
                  <div key={idx} className={`flex justify-between items-start border-b border-slate-900 pb-2 hover:bg-slate-900/40 p-1.5 rounded-lg transition-all duration-150 ${!entry.allowed ? "bg-rose-950/20 text-rose-300 border-l-2 border-l-rose-550 pl-3" : ""}`}>
                    <div className="flex flex-wrap gap-x-4">
                      <span className="text-slate-600 select-none shrink-0">{formatTime(entry.ts)}</span>
                      <span className={`font-bold shrink-0 text-[10px] uppercase tracking-wider ${entry.allowed ? "text-emerald-400" : "text-rose-400 animate-pulse"}`}>
                        [{entry.allowed ? "ALLOWED" : "BLOCKED"}]
                      </span>
                      <span className="text-teal-400 font-bold shrink-0">{entry.tool}</span>
                      <span className="text-slate-400">({entry.reason})</span>
                      {entry.arg_keys && entry.arg_keys.length > 0 && (
                        <span className="text-slate-550 text-[10px]">keys: {entry.arg_keys.join(", ")}</span>
                      )}
                    </div>
                    <button
                      onClick={() => handleCopyLogs(logText, idx)}
                      className="text-slate-550 hover:text-white p-0.5 hover:bg-slate-800 rounded transition shrink-0 ml-4"
                      title="Copy entry"
                    >
                      {copiedIndex === idx ? <Check className="h-3.5 w-3.5 text-emerald-450" /> : <Copy className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                );
              })
            )}
            <div ref={liveLogsEndRef} />
          </div>
        </div>
      )}
    </div>
  );
}
