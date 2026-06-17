"use client";

import { useEffect, useState, useRef } from "react";
import { fetchAPI, WS_URL } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState } from "@/components/EmptyState";
import { MarkdownRenderer } from "@/components/MarkdownRenderer";
import { useToast } from "@/components/Toast";
import { 
  Activity, 
  Terminal, 
  Sparkles, 
  RefreshCw, 
  ArrowRight,
  Calendar
} from "lucide-react";
import Link from "next/link";

interface Repo {
  id: string;
  type: "github" | "gitlab" | "jenkins" | "azure";
  name: string;
  extra?: Record<string, any>;
}

interface AzureRun {
  id: number;
  name: string;
  state: string;
  result: string;
  createdDate: string;
  url: string;
}

export default function AzurePage() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<Repo | null>(null);
  const [runs, setRuns] = useState<AzureRun[]>([]);
  const [loading, setLoading] = useState(false);

  // Log and AI Analysis states
  const [viewingRunId, setViewingRunId] = useState<number | null>(null);
  const [runLogs, setRunLogs] = useState("");
  const [logsLoading, setLogsLoading] = useState(false);
  const [aiAnalysis, setAiAnalysis] = useState("");
  const [aiLoading, setAiLoading] = useState(false);

  const { toast } = useToast();
  const wsRef = useRef<WebSocket | null>(null);

  const loadRepos = async () => {
    try {
      const data = await fetchAPI("/api/repos");
      const azRepos = data.filter((r: Repo) => r.type === "azure");
      setRepos(azRepos);
      if (azRepos.length > 0) {
        setSelectedRepo(azRepos[0]);
      }
    } catch (err) {
      toast("Failed to load Azure DevOps repositories.", "error");
    }
  };

  useEffect(() => {
    loadRepos();
  }, []);

  const loadRunDetails = async (repo: Repo) => {
    if (!repo) return;
    setLoading(true);
    const pipelineId = repo.extra?.pipeline_id || 0;
    try {
      const data = await fetchAPI(`/api/azure/${repo.name}/${pipelineId}/runs`);
      setRuns(data || []);
    } catch (err) {
      toast("Failed to load Azure pipeline runs.", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedRepo) {
      loadRunDetails(selectedRepo);
      setViewingRunId(null);
      setRunLogs("");
      setAiAnalysis("");
    }
  }, [selectedRepo]);

  const handleFetchLogs = async (runId: number) => {
    if (!selectedRepo) return;
    setViewingRunId(runId);
    setRunLogs("");
    setAiAnalysis("");
    setLogsLoading(true);

    const pipelineId = selectedRepo.extra?.pipeline_id || 0;
    try {
      const logsText = await fetchAPI(`/api/azure/${selectedRepo.name}/${pipelineId}/runs/${runId}/logs`, {
        headers: { Accept: "text/plain" }
      });
      setRunLogs(logsText);
      toast("Console execution logs fetched", "success");
    } catch (err: any) {
      setRunLogs(err.message || "Failed to download logs.");
      toast("Failed to fetch logs", "error");
    } finally {
      setLogsLoading(false);
    }
  };

  const handleAnalyzeLogs = async () => {
    if (!runLogs || !selectedRepo) return;
    setAiLoading(true);
    setAiAnalysis("");
    toast("AI diagnostics started", "info");

    try {
      const run = runs.find((r) => r.id === viewingRunId);

      const triggerRes = await fetchAPI("/api/analysis/log", {
        method: "POST",
        body: JSON.stringify({
          log: runLogs,
          platform: "Azure DevOps",
          repo: selectedRepo.name,
          job: run?.name || "Pipeline run",
          trigger: "azure devops trigger"
        })
      });

      const analysisId = triggerRes.analysis_id;

      // Connect to WebSocket to stream tokens
      const ws = new WebSocket(`${WS_URL}/ws/analysis/${analysisId}`);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        setAiAnalysis((prev) => prev + event.data);
      };

      ws.onclose = () => {
        setAiLoading(false);
        toast("Diagnostic analysis complete", "success");
      };
    } catch (err: any) {
      setAiAnalysis(`AI Analysis Error: ${err.message}`);
      setAiLoading(false);
      toast("Failed to analyze logs", "error");
    }
  };

  const formatTime = (isoString: string) => {
    if (!isoString) return "-";
    const date = new Date(isoString);
    return date.toLocaleTimeString() + " " + date.toLocaleDateString();
  };

  return (
    <div className="space-y-6 animate-fade-slide-up">
      {/* Selector Banner */}
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 bg-white border border-slate-200 p-5 rounded-2xl shadow-xs">
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <span className="font-bold text-slate-800 text-xs uppercase tracking-wider">Select Azure DevOps Project:</span>
          {repos.length === 0 ? (
            <span className="text-slate-400 text-xs italic">No Azure DevOps projects configured.</span>
          ) : (
            <select
              value={selectedRepo?.name || ""}
              onChange={(e) => {
                const found = repos.find((r) => r.name === e.target.value);
                if (found) setSelectedRepo(found);
              }}
              className="border border-slate-255 rounded-xl px-3.5 py-2 text-xs font-semibold focus:outline-none focus:border-teal-500 bg-white"
            >
              {repos.map((r) => (
                <option key={r.id} value={r.name}>{r.name} (Pipeline ID: {r.extra?.pipeline_id})</option>
              ))}
            </select>
          )}
        </div>
        
        <Link href="/repos" className="text-xs text-teal-600 font-bold hover:underline flex items-center gap-1">
          Manage Configurations
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>

      {repos.length === 0 ? (
        <div className="py-8">
          <EmptyState
            title="Configure Azure DevOps Projects"
            description="Add your project configuration under Repositories using project name, Pipeline ID, and Personal Access Token."
            actionLabel="Add Azure DevOps Project"
            onAction={() => window.location.href = "/repos"}
          />
        </div>
      ) : selectedRepo && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          
          {/* Runs list */}
          <div className="lg:col-span-7 bg-white border border-slate-200 rounded-2xl shadow-xs overflow-hidden h-fit">
            <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
              <h3 className="font-bold text-slate-800 text-sm flex items-center gap-2">
                <Activity className="h-4.5 w-4.5 text-blue-600 animate-pulse" />
                Azure DevOps Runs
              </h3>
              <button
                onClick={() => loadRunDetails(selectedRepo)}
                disabled={loading}
                className="text-xs text-teal-600 hover:text-teal-700 font-bold flex items-center gap-1 disabled:opacity-50"
              >
                <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
                Refresh
              </button>
            </div>

            {loading ? (
              <div className="p-8 space-y-4">
                {[1, 2, 3].map((n) => (
                  <div key={n} className="h-16 bg-slate-50 border border-slate-100 rounded-2xl animate-shimmer" />
                ))}
              </div>
            ) : runs.length === 0 ? (
              <div className="p-8">
                <EmptyState
                  title="No pipeline runs"
                  description="Could not find any run execution history on this Azure DevOps project pipeline."
                />
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {runs.map((run) => (
                  <div
                    key={run.id}
                    className={`p-4 flex justify-between items-center gap-4 transition duration-150 ${
                      viewingRunId === run.id ? "bg-slate-50/70" : "hover:bg-slate-50/30"
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <StatusBadge value={run.result || run.state} />
                        <span className="text-[10px] text-slate-400 font-mono">#{run.id}</span>
                      </div>
                      <h4 className="font-bold text-slate-800 text-xs mt-2 truncate" title={run.name}>
                        {run.name}
                      </h4>
                      <p className="text-slate-500 text-[10px] mt-1.5 flex items-center gap-1.5">
                        <Calendar className="h-3.5 w-3.5 text-slate-400" />
                        Created: {formatTime(run.createdDate)}
                      </p>
                    </div>

                    <div className="flex gap-2 shrink-0">
                      <button
                        onClick={() => handleFetchLogs(run.id)}
                        className={`px-3 py-1.5 border border-slate-350 hover:bg-slate-50 hover:border-slate-400 text-slate-700 font-semibold text-[10px] rounded-xl transition duration-150 ${logsLoading && viewingRunId === run.id ? "opacity-50 pointer-events-none" : ""}`}
                      >
                        {logsLoading && viewingRunId === run.id ? "Loading..." : "Console Output"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Right Log Viewer and AI Analysis */}
          <div className="lg:col-span-5 space-y-6">
            {viewingRunId === null ? (
              <div className="border border-dashed border-slate-350 rounded-2xl bg-white/50 p-8 text-center text-slate-400 text-xs flex flex-col items-center justify-center min-h-[350px]">
                <div className="p-3 bg-slate-100 text-slate-400 rounded-full mb-3 shadow-xs">
                  <Terminal className="h-6 w-6" />
                </div>
                <h4 className="font-bold text-slate-700 text-sm">Select run logs</h4>
                <p className="mt-1.5 max-w-xs leading-relaxed">Click "Console Output" on any pipeline run block to view pipeline logs and trigger AI diagnoses.</p>
              </div>
            ) : (
              <div className="space-y-6 sticky top-6">
                
                {/* Console Log */}
                <div className="bg-slate-950 rounded-2xl border border-slate-800 shadow-lg flex flex-col max-h-[350px] overflow-hidden">
                  <div className="bg-slate-900/80 px-4 py-3 border-b border-slate-800 flex justify-between items-center">
                    <span className="text-slate-400 text-[10px] font-bold tracking-wider flex items-center gap-1.5 font-mono">
                      <Terminal className="h-4 w-4 text-teal-500 animate-pulse" />
                      PIPELINE EXECUTION TRACES
                    </span>
                    {runLogs && !logsLoading && (
                      <button
                        onClick={handleAnalyzeLogs}
                        disabled={aiLoading}
                        className="bg-teal-600 hover:bg-teal-700 disabled:bg-teal-500 text-white font-bold text-[10px] px-3 py-1.5 rounded-xl transition duration-150 flex items-center gap-1 shadow-xs"
                      >
                        <Sparkles className="h-3 w-3" />
                        {aiLoading ? "Analyzing..." : "Diagnose Logs"}
                      </button>
                    )}
                  </div>

                  <div className="flex-1 p-5 font-mono text-[11px] text-slate-300 bg-slate-950 overflow-y-auto whitespace-pre-wrap select-text selection:bg-slate-850 h-[300px]">
                    {logsLoading ? (
                      <div className="flex items-center justify-center h-full gap-2 text-slate-500">
                        <RefreshCw className="h-4 w-4 animate-spin text-teal-600" />
                        <span className="italic font-medium">Downloading execution logs...</span>
                      </div>
                    ) : (
                      runLogs || "No logs available."
                    )}
                  </div>
                </div>

                {/* AI Analysis Panel */}
                {(aiLoading || aiAnalysis) && (
                  <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm flex flex-col space-y-4">
                    <div className="flex justify-between items-center border-b border-slate-100 pb-3">
                      <h4 className="font-bold text-slate-800 text-xs flex items-center gap-1.5">
                        <Sparkles className="h-4 w-4 text-teal-600" />
                        AI Analysis Report
                      </h4>
                      {aiLoading && (
                        <span className="text-[10px] font-medium text-teal-600 animate-pulse">Streaming chunks...</span>
                      )}
                    </div>

                    <div className="bg-teal-50/10 border border-teal-150 p-4 rounded-xl">
                      <MarkdownRenderer 
                        content={aiAnalysis} 
                        isStreaming={aiLoading} 
                      />
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
