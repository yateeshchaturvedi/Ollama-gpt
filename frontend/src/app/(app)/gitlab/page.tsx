"use client";

import { useEffect, useState, useRef } from "react";
import { fetchAPI, WS_URL } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState } from "@/components/EmptyState";
import { MarkdownRenderer } from "@/components/MarkdownRenderer";
import { useToast } from "@/components/Toast";
import { 
  Terminal, 
  Sparkles, 
  RefreshCw, 
  ArrowRight,
  GitBranch
} from "lucide-react";

// Custom SVG Brand Icons since they are not exported by the installed version of lucide-react
const GitlabIcon = ({ className }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="m22 13.29-3.33-10a.42.42 0 0 0-.14-.18.38.38 0 0 0-.22-.1.39.39 0 0 0-.23.07.42.42 0 0 0-.14.18l-2.26 6.67H8.32L6.06 3.26a.42.42 0 0 0-.14-.18.38.38 0 0 0-.22-.1.39.39 0 0 0-.23.07.42.42 0 0 0-.14.18L2 13.29a.74.74 0 0 0 .27.83L12 21l9.69-6.88a.71.71 0 0 0 .31-.83Z" />
  </svg>
);

import Link from "next/link";

interface Repo {
  id: string;
  type: "github" | "gitlab" | "jenkins" | "azure";
  name: string;
}

interface GitLabPipeline {
  id: number;
  status: string;
  ref: string;
  web_url: string;
  created_at: string;
}

export default function GitLabPage() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [selectedRepo, setSelectedRepo] = useState("");
  const [pipelines, setPipelines] = useState<GitLabPipeline[]>([]);
  const [loading, setLoading] = useState(false);

  // Log and AI Analysis states
  const [viewingPipelineId, setViewingPipelineId] = useState<number | null>(null);
  const [pipelineLogs, setPipelineLogs] = useState("");
  const [logsLoading, setLogsLoading] = useState(false);
  const [aiAnalysis, setAiAnalysis] = useState("");
  const [aiLoading, setAiLoading] = useState(false);

  const { toast } = useToast();
  const wsRef = useRef<WebSocket | null>(null);

  const loadRepos = async () => {
    try {
      const data = await fetchAPI("/api/repos");
      const glRepos = data.filter((r: Repo) => r.type === "gitlab");
      setRepos(glRepos);
      if (glRepos.length > 0) {
        setSelectedRepo(glRepos[0].name);
      }
    } catch (err) {
      toast("Failed to load GitLab repositories.", "error");
    }
  };

  useEffect(() => {
    loadRepos();
  }, []);

  const loadPipelineDetails = async (repoName: string) => {
    if (!repoName) return;
    setLoading(true);
    try {
      const data = await fetchAPI(`/api/gitlab/${repoName}/pipelines`);
      setPipelines(data || []);
    } catch (err) {
      toast("Failed to load GitLab pipelines", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedRepo) {
      loadPipelineDetails(selectedRepo);
      setViewingPipelineId(null);
      setPipelineLogs("");
      setAiAnalysis("");
    }
  }, [selectedRepo]);

  const handleFetchLogs = async (pipelineId: number) => {
    setViewingPipelineId(pipelineId);
    setPipelineLogs("");
    setAiAnalysis("");
    setLogsLoading(true);

    try {
      const logsText = await fetchAPI(`/api/gitlab/${selectedRepo}/pipelines/${pipelineId}/logs`, {
        headers: { Accept: "text/plain" }
      });
      setPipelineLogs(logsText);
      toast("Pipeline logs downloaded successfully", "success");
    } catch (err: any) {
      setPipelineLogs(err.message || "Failed to download logs.");
      toast("Failed to fetch logs", "error");
    } finally {
      setLogsLoading(false);
    }
  };

  const handleAnalyzeLogs = async () => {
    if (!pipelineLogs) return;
    setAiLoading(true);
    setAiAnalysis("");
    toast("AI diagnostics started", "info");

    try {
      const pipe = pipelines.find((p) => p.id === viewingPipelineId);

      const triggerRes = await fetchAPI("/api/analysis/log", {
        method: "POST",
        body: JSON.stringify({
          log: pipelineLogs,
          platform: "GitLab CI",
          repo: selectedRepo,
          job: `Pipeline #${viewingPipelineId}`,
          trigger: pipe?.ref || "unknown"
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

  return (
    <div className="space-y-6 animate-fade-slide-up">
      {/* Selector Banner */}
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 bg-white border border-slate-200 p-5 rounded-2xl shadow-xs">
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <span className="font-bold text-slate-800 text-xs uppercase tracking-wider">Select GitLab Project:</span>
          {repos.length === 0 ? (
            <span className="text-slate-400 text-xs italic">No GitLab projects configured.</span>
          ) : (
            <select
              value={selectedRepo}
              onChange={(e) => setSelectedRepo(e.target.value)}
              className="border border-slate-255 rounded-xl px-3.5 py-2 text-xs font-semibold focus:outline-none focus:border-teal-500 bg-white"
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
            title="Configure GitLab Projects"
            description="Add your project configuration under Repositories using your GitLab Project ID or URL-encoded path and Access Token."
            actionLabel="Add GitLab Project"
            onAction={() => window.location.href = "/repos"}
          />
        </div>
      ) : selectedRepo && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          
          {/* Pipelines list */}
          <div className="lg:col-span-7 bg-white border border-slate-200 rounded-2xl shadow-xs overflow-hidden h-fit">
            <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
              <h3 className="font-bold text-slate-800 text-sm flex items-center gap-2">
                <GitlabIcon className="h-4.5 w-4.5 text-orange-600" />
                GitLab CI Pipelines
              </h3>
              <button
                onClick={() => loadPipelineDetails(selectedRepo)}
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
            ) : pipelines.length === 0 ? (
              <div className="p-8">
                <EmptyState
                  title="No pipelines"
                  description="Could not find any pipeline execution history on this project."
                />
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {pipelines.map((pipe) => (
                  <div
                    key={pipe.id}
                    className={`p-4 flex justify-between items-center gap-4 transition duration-150 ${
                      viewingPipelineId === pipe.id ? "bg-slate-50/70" : "hover:bg-slate-50/30"
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <StatusBadge value={pipe.status === "failed" ? "failed" : pipe.status === "success" ? "success" : "running"} />
                        <span className="text-[10px] text-slate-400 font-mono">#{pipe.id}</span>
                      </div>
                      <p className="text-slate-500 text-[10px] mt-2 flex items-center gap-2">
                        <span className="flex items-center gap-1">
                          <GitBranch className="h-3 w-3 text-slate-400" />
                          ref: <span className="font-mono bg-slate-100 px-1 py-0.5 rounded text-slate-700">{pipe.ref}</span>
                        </span>
                        <span className="text-slate-300">|</span>
                        <span>created: {new Date(pipe.created_at).toLocaleTimeString()}</span>
                      </p>
                    </div>

                    <div className="flex gap-2 shrink-0">
                      <button
                        onClick={() => handleFetchLogs(pipe.id)}
                        className={`px-3 py-1.5 border border-slate-350 hover:bg-slate-50 hover:border-slate-400 text-slate-700 font-semibold text-[10px] rounded-xl transition duration-150 ${logsLoading && viewingPipelineId === pipe.id ? "opacity-50 pointer-events-none" : ""}`}
                      >
                        {logsLoading && viewingPipelineId === pipe.id ? "Loading..." : "View Trace"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Right Log Viewer and AI Analysis */}
          <div className="lg:col-span-5 space-y-6">
            {viewingPipelineId === null ? (
              <div className="border border-dashed border-slate-350 rounded-2xl bg-white/50 p-8 text-center text-slate-400 text-xs flex flex-col items-center justify-center min-h-[350px]">
                <div className="p-3 bg-slate-100 text-slate-400 rounded-full mb-3 shadow-xs">
                  <Terminal className="h-6 w-6" />
                </div>
                <h4 className="font-bold text-slate-700 text-sm">Select pipeline trace</h4>
                <p className="mt-1.5 max-w-xs leading-relaxed">Click "View Trace" on any pipeline block to load the job log and trigger AI diagnostic reviews.</p>
              </div>
            ) : (
              <div className="space-y-6 sticky top-6">
                
                {/* Console Log */}
                <div className="bg-slate-950 rounded-2xl border border-slate-800 shadow-lg flex flex-col max-h-[350px] overflow-hidden">
                  <div className="bg-slate-900/80 px-4 py-3 border-b border-slate-800 flex justify-between items-center">
                    <span className="text-slate-400 text-[10px] font-bold tracking-wider flex items-center gap-1.5 font-mono">
                      <Terminal className="h-4 w-4 text-teal-500 animate-pulse" />
                      PIPELINE TRACE OUTPUT
                    </span>
                    {pipelineLogs && !logsLoading && (
                      <button
                        onClick={handleAnalyzeLogs}
                        disabled={aiLoading}
                        className="bg-teal-600 hover:bg-teal-700 disabled:bg-teal-500 text-white font-bold text-[10px] px-3 py-1.5 rounded-xl transition duration-150 flex items-center gap-1 shadow-xs"
                      >
                        <Sparkles className="h-3 w-3" />
                        {aiLoading ? "Analyzing..." : "Diagnose Trace"}
                      </button>
                    )}
                  </div>

                  <div className="flex-1 p-5 font-mono text-[11px] text-slate-300 bg-slate-950 overflow-y-auto whitespace-pre-wrap select-text selection:bg-slate-850 h-[300px]">
                    {logsLoading ? (
                      <div className="flex items-center justify-center h-full gap-2 text-slate-500">
                        <RefreshCw className="h-4 w-4 animate-spin text-teal-600" />
                        <span className="italic font-medium">Downloading pipeline logs...</span>
                      </div>
                    ) : (
                      pipelineLogs || "No trace data available."
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
