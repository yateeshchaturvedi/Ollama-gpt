"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { fetchAPI, WS_URL } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState } from "@/components/EmptyState";
import { MarkdownRenderer } from "@/components/MarkdownRenderer";
import { useToast } from "@/components/Toast";
import { 
  GitFork, 
  GitPullRequest, 
  Terminal, 
  Sparkles, 
  RefreshCw, 
  ArrowRight,
  ExternalLink,
  Ban
} from "lucide-react";

// Custom SVG Brand Icons since they are not exported by the installed version of lucide-react
const GithubIcon = ({ className }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
    <path d="M9 18c-4.51 2-5-2-7-2" />
  </svg>
);


interface Repo {
  id: string;
  type: "github" | "gitlab" | "jenkins" | "azure";
  name: string;
}

interface WorkflowRun {
  id: number;
  name: string;
  status: string;
  conclusion: string;
  head_branch: string;
  event: string;
  html_url: string;
  created_at: string;
}

interface PullRequest {
  number: number;
  title: string;
  state: string;
  html_url: string;
  user: { login: string };
  created_at: string;
}

export default function GitHubPage() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [selectedRepo, setSelectedRepo] = useState("");
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [prs, setPrs] = useState<PullRequest[]>([]);
  const [loading, setLoading] = useState(false);

  // Log and AI Analysis states
  const [viewingRunId, setViewingRunId] = useState<number | null>(null);
  const [runLogs, setRunLogs] = useState("");
  const [logsLoading, setLogsLoading] = useState(false);
  const [aiAnalysis, setAiAnalysis] = useState("");
  const [aiLoading, setAiLoading] = useState(false);

  // Button loader states
  const [actionInProgress, setActionInProgress] = useState<number | null>(null);

  const { toast } = useToast();
  const wsRef = useRef<WebSocket | null>(null);

  const loadRepos = async () => {
    try {
      const data = await fetchAPI("/api/repos");
      const ghRepos = data.filter((r: Repo) => r.type === "github");
      setRepos(ghRepos);
      if (ghRepos.length > 0) {
        setSelectedRepo(ghRepos[0].name);
      }
    } catch (err) {
      toast("Failed to load GitHub repositories.", "error");
    }
  };

  useEffect(() => {
    loadRepos();
  }, []);

  const loadRepoDetails = async (repoName: string) => {
    if (!repoName) return;
    setLoading(true);
    const [owner, repo] = repoName.split("/");
    try {
      const [runsData, prsData] = await Promise.all([
        fetchAPI(`/api/github/${owner}/${repo}/runs`),
        fetchAPI(`/api/github/${owner}/${repo}/prs`)
      ]);
      setRuns(runsData.workflow_runs || []);
      setPrs(prsData || []);
    } catch (err) {
      toast("Failed to fetch workflow runs or pull requests", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedRepo) {
      loadRepoDetails(selectedRepo);
      // Close log panels on repo swap
      setViewingRunId(null);
      setRunLogs("");
      setAiAnalysis("");
    }
  }, [selectedRepo]);

  const handleFetchLogs = async (runId: number) => {
    setViewingRunId(runId);
    setRunLogs("");
    setAiAnalysis("");
    setLogsLoading(true);

    const [owner, repo] = selectedRepo.split("/");
    try {
      const logsText = await fetchAPI(`/api/github/${owner}/${repo}/runs/${runId}/logs`, {
        headers: { Accept: "text/plain" }
      });
      setRunLogs(logsText);
      toast("Run logs loaded successfully", "success");
    } catch (err: any) {
      setRunLogs(err.message || "Failed to download log files.");
      toast("Failed to fetch logs", "error");
    } finally {
      setLogsLoading(false);
    }
  };

  const handleRetryRun = async (runId: number) => {
    setActionInProgress(runId);
    const [owner, repo] = selectedRepo.split("/");
    try {
      await fetchAPI(`/api/github/${owner}/${repo}/runs/${runId}/retry`, { method: "POST" });
      toast("Rebuild workflow run successfully triggered", "success");
      loadRepoDetails(selectedRepo);
    } catch (err: any) {
      toast(err.message || "Failed to retry workflow.", "error");
    } finally {
      setActionInProgress(null);
    }
  };

  const handleCancelRun = async (runId: number) => {
    setActionInProgress(runId);
    const [owner, repo] = selectedRepo.split("/");
    try {
      await fetchAPI(`/api/github/${owner}/${repo}/runs/${runId}/cancel`, { method: "POST" });
      toast("Workflow cancellation request sent", "info");
      loadRepoDetails(selectedRepo);
    } catch (err: any) {
      toast(err.message || "Failed to cancel workflow.", "error");
    } finally {
      setActionInProgress(null);
    }
  };

  const handleAnalyzeLogs = async () => {
    if (!runLogs) return;
    setAiLoading(true);
    setAiAnalysis("");
    toast("AI diagnostic analysis started", "info");

    try {
      const [owner, repo] = selectedRepo.split("/");
      const run = runs.find((r) => r.id === viewingRunId);

      const triggerRes = await fetchAPI("/api/analysis/log", {
        method: "POST",
        body: JSON.stringify({
          log: runLogs,
          platform: "GitHub Actions",
          repo: selectedRepo,
          job: run?.name || "Workflow run",
          trigger: run?.event || "unknown"
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
      toast("Failed to stream AI analysis", "error");
    }
  };

  return (
    <div className="space-y-6 animate-fade-slide-up">
      {/* Selector banner */}
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 bg-white border border-slate-200 p-5 rounded-2xl shadow-xs">
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <span className="font-bold text-slate-800 text-xs uppercase tracking-wider">Select Repository:</span>
          {repos.length === 0 ? (
            <span className="text-slate-400 text-xs italic">No GitHub repos configured.</span>
          ) : (
            <select
              value={selectedRepo}
              onChange={(e) => setSelectedRepo(e.target.value)}
              className="border border-slate-250 rounded-xl px-3.5 py-2 text-xs font-semibold focus:outline-none focus:border-teal-500 bg-white"
            >
              {repos.map((r) => (
                <option key={r.id} value={r.name}>{r.name}</option>
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
            title="Configure GitHub Repositories"
            description="Add your repository config under Repositories using your GitHub owner/name and Personal Access Token."
            actionLabel="Add GitHub Repo"
            onAction={() => window.location.href = "/repos"}
          />
        </div>
      ) : selectedRepo && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          
          {/* Workflow Runs list */}
          <div className="lg:col-span-7 space-y-6">
            <div className="bg-white border border-slate-200 rounded-2xl shadow-xs overflow-hidden">
              <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
                <h3 className="font-bold text-slate-800 text-sm flex items-center gap-2">
                  <GithubIcon className="h-4.5 w-4.5 text-slate-900" />
                  Recent Workflow Runs
                </h3>
                <button
                  onClick={() => loadRepoDetails(selectedRepo)}
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
                    title="No workflow runs"
                    description="Could not find workflow execution runs on this repository."
                  />
                </div>
              ) : (
                <div className="divide-y divide-slate-100">
                  {runs.map((run) => (
                    <div
                      key={run.id}
                      className={`p-4 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 transition duration-150 ${
                        viewingRunId === run.id ? "bg-slate-50/70" : "hover:bg-slate-50/30"
                      }`}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <StatusBadge value={run.conclusion || run.status} />
                          <span className="text-[10px] text-slate-400 font-mono">#{run.id}</span>
                        </div>
                        <h4 className="font-bold text-slate-800 text-xs mt-2 truncate" title={run.name}>
                          {run.name}
                        </h4>
                        <p className="text-slate-500 text-[10px] mt-1 flex items-center gap-2">
                          <span>branch: <span className="font-mono bg-slate-100 px-1 py-0.5 rounded text-slate-700">{run.head_branch}</span></span>
                          <span className="text-slate-350">|</span>
                          <span>trigger: <span className="font-semibold text-slate-600 capitalize">{run.event}</span></span>
                        </p>
                      </div>

                      <div className="flex gap-2 shrink-0">
                        <button
                          onClick={() => handleFetchLogs(run.id)}
                          className={`px-3 py-1.5 border border-slate-300 hover:bg-slate-50 hover:border-slate-400 text-slate-700 font-semibold text-[10px] rounded-xl transition duration-150 ${logsLoading && viewingRunId === run.id ? "opacity-50 pointer-events-none" : ""}`}
                        >
                          {logsLoading && viewingRunId === run.id ? "Loading..." : "View Logs"}
                        </button>
                        {run.status === "completed" && run.conclusion === "failure" && (
                          <button
                            onClick={() => handleRetryRun(run.id)}
                            disabled={actionInProgress !== null}
                            className="px-3 py-1.5 bg-teal-600 hover:bg-teal-700 text-white font-semibold text-[10px] rounded-xl shadow-xs transition duration-150 flex items-center gap-1"
                          >
                            {actionInProgress === run.id ? <RefreshCw className="h-3 w-3 animate-spin" /> : null}
                            Rebuild
                          </button>
                        )}
                        {run.status === "in_progress" && (
                          <button
                            onClick={() => handleCancelRun(run.id)}
                            disabled={actionInProgress !== null}
                            className="px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white font-semibold text-[10px] rounded-xl shadow-xs transition duration-150 flex items-center gap-1"
                          >
                            {actionInProgress === run.id ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Ban className="h-3 w-3" />}
                            Cancel
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Pull Requests */}
            <div className="bg-white border border-slate-200 rounded-2xl shadow-xs overflow-hidden">
              <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50">
                <h3 className="font-bold text-slate-800 text-sm flex items-center gap-2">
                  <GitPullRequest className="h-4.5 w-4.5 text-teal-600" />
                  Active Pull Requests
                </h3>
              </div>
              <div className="divide-y divide-slate-100 max-h-60 overflow-y-auto">
                {prs.length === 0 ? (
                  <div className="py-8 text-center text-slate-400 text-xs italic">No open pull requests.</div>
                ) : (
                  prs.map((pr) => (
                    <div key={pr.number} className="p-4 hover:bg-slate-50/20 transition flex justify-between items-center gap-4">
                      <div className="min-w-0">
                        <h4 className="font-semibold text-slate-800 text-xs truncate" title={pr.title}>
                          #{pr.number} {pr.title}
                        </h4>
                        <span className="text-[10px] text-slate-400 mt-1 block">Author: {pr.user?.login}</span>
                      </div>
                      <a
                        href={pr.html_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-teal-600 hover:underline font-bold text-[10px] shrink-0 flex items-center gap-1 bg-teal-50 border border-teal-150 px-2 py-1 rounded-lg hover:bg-teal-100 transition"
                      >
                        PR link
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* Right Log Viewer and AI Analysis */}
          <div className="lg:col-span-5 space-y-6">
            {viewingRunId === null ? (
              <div className="border border-dashed border-slate-350 rounded-2xl bg-white/50 p-8 text-center text-slate-400 text-xs flex flex-col items-center justify-center min-h-[350px]">
                <div className="p-3 bg-slate-100 text-slate-400 rounded-full mb-3 shadow-xs">
                  <Terminal className="h-6 w-6" />
                </div>
                <h4 className="font-bold text-slate-700 text-sm">Select build logs</h4>
                <p className="mt-1.5 max-w-xs leading-relaxed">Click "View Logs" on any run block to load the execution stream traces and enable AI diagnoses.</p>
              </div>
            ) : (
              <div className="space-y-6 sticky top-6">
                
                {/* Console Log Log-Viewer */}
                <div className="bg-slate-950 rounded-2xl border border-slate-800 shadow-lg flex flex-col max-h-[350px] overflow-hidden">
                  <div className="bg-slate-900/80 px-4 py-3 border-b border-slate-800 flex justify-between items-center">
                    <span className="text-slate-400 text-[10px] font-bold tracking-wider flex items-center gap-1.5 font-mono">
                      <Terminal className="h-4 w-4 text-teal-500 animate-pulse" />
                      CONSOLE OUTPUT LOGS
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
                        <span className="italic font-medium">Downloading job runs log...</span>
                      </div>
                    ) : (
                      runLogs || "No logs available."
                    )}
                  </div>
                </div>

                {/* AI Diagnostic Output */}
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
