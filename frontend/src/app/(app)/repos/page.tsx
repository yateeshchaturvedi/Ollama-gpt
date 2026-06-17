"use client";

import { useEffect, useState } from "react";
import { fetchAPI } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState } from "@/components/EmptyState";
import { useToast } from "@/components/Toast";
import { 
  Eye, 
  EyeOff, 
  Trash2, 
  Plus, 
  X, 
  FolderKanban, 
  Settings2,
  Lock,
  Globe,
  Hash,
  Activity,
  Layers
} from "lucide-react";

interface Repo {
  id: string;
  type: "github" | "gitlab" | "jenkins" | "azure";
  name: string;
  url?: string;
  credential_id?: string;
  extra?: Record<string, any>;
}

interface Credential {
  id: string;
  platform: string;
  label: string;
  token_hint: string;
}

interface DiscoverItem {
  name: string;
  url?: string;
  already_added: boolean;
}

const platformColors = {
  github: { bg: "bg-slate-800", border: "border-slate-700", glow: "hover:shadow-[0_0_15px_rgba(100,116,139,0.3)]", accent: "bg-slate-300" },
  gitlab: { bg: "bg-orange-950/30", border: "border-orange-900/50", glow: "hover:shadow-[0_0_15px_rgba(234,88,12,0.2)]", accent: "bg-orange-500" },
  jenkins: { bg: "bg-rose-950/30", border: "border-rose-900/50", glow: "hover:shadow-[0_0_15px_rgba(225,29,72,0.2)]", accent: "bg-rose-500" },
  azure: { bg: "bg-blue-950/30", border: "border-blue-900/50", glow: "hover:shadow-[0_0_15px_rgba(37,99,235,0.2)]", accent: "bg-blue-500" }
};

export default function ReposPage() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [loading, setLoading] = useState(true);

  // Form states
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingRepo, setEditingRepo] = useState<Repo | null>(null);
  
  const [type, setType] = useState<"github" | "gitlab" | "jenkins" | "azure">("github");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [credentialId, setCredentialId] = useState("");
  const [extraPipelineId, setExtraPipelineId] = useState("");
  
  // Discovery states
  const [showDiscoverModal, setShowDiscoverModal] = useState(false);
  const [discoverLoading, setDiscoverLoading] = useState(false);
  const [discoveredRepos, setDiscoveredRepos] = useState<DiscoverItem[]>([]);
  const [selectedDiscoverNames, setSelectedDiscoverNames] = useState<Set<string>>(new Set());

  // Delete Confirmation state
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const { toast } = useToast();

  const loadData = async () => {
    setLoading(true);
    try {
      const [reposData, credsData] = await Promise.all([
        fetchAPI("/api/repos"),
        fetchAPI("/api/admin/credentials").catch(() => []) // Only works for admins, fallback to []
      ]);
      setRepos(reposData);
      setCredentials(credsData);
    } catch (err: any) {
      toast(err.message || "Failed to load repositories.", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleOpenAdd = () => {
    setEditingRepo(null);
    setType("github");
    setName("");
    setUrl("");
    setCredentialId("");
    setExtraPipelineId("");
    setShowAddModal(true);
  };

  const handleOpenEdit = (repo: Repo) => {
    setEditingRepo(repo);
    setType(repo.type);
    setName(repo.name);
    setUrl(repo.url || "");
    setCredentialId(repo.credential_id || "");
    setExtraPipelineId(repo.extra?.pipeline_id ? String(repo.extra.pipeline_id) : "");
    setShowAddModal(true);
  };
  
  const handleOpenDiscover = () => {
    setType("github");
    setCredentialId("");
    setDiscoveredRepos([]);
    setSelectedDiscoverNames(new Set());
    setShowDiscoverModal(true);
  };

  const handleDiscover = async () => {
    if (!credentialId) {
      toast("Please select a credential first", "warning");
      return;
    }
    setDiscoverLoading(true);
    try {
      const data = await fetchAPI(`/api/repos/discover?platform=${type}&credential_id=${credentialId}`);
      setDiscoveredRepos(data);
      setSelectedDiscoverNames(new Set());
    } catch (err: any) {
      toast(err.message || "Failed to discover repositories.", "error");
    } finally {
      setDiscoverLoading(false);
    }
  };

  const handleBulkImport = async () => {
    if (selectedDiscoverNames.size === 0) return;
    
    try {
      await fetchAPI("/api/repos/import", {
        method: "POST",
        body: JSON.stringify({
          platform: type,
          names: Array.from(selectedDiscoverNames),
          credential_id: credentialId
        })
      });
      toast(`Successfully imported ${selectedDiscoverNames.size} repositories`, "success");
      setShowDiscoverModal(false);
      loadData();
    } catch (err: any) {
      toast(err.message || "Failed to import repositories.", "error");
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      toast("Repository identifier name is required", "warning");
      return;
    }

    if (type !== "github" && url.trim() !== "" && !url.trim().startsWith("http")) {
      toast("Please provide a valid URL starting with http/https", "warning");
      return;
    }

    const extra: Record<string, any> = {};
    if (type === "azure") {
      const pipelineIdInt = parseInt(extraPipelineId, 10);
      if (isNaN(pipelineIdInt)) {
        toast("Azure Pipeline ID must be a numeric integer", "warning");
        return;
      }
      extra.pipeline_id = pipelineIdInt;
    }

    const payload = {
      type,
      name: name.trim(),
      url: url.trim() || undefined,
      credential_id: credentialId || undefined,
      extra
    };

    try {
      if (editingRepo) {
        await fetchAPI(`/api/repos/${editingRepo.id}`, {
          method: "PUT",
          body: JSON.stringify(payload)
        });
        toast("Repository settings updated successfully", "success");
      } else {
        await fetchAPI("/api/repos", {
          method: "POST",
          body: JSON.stringify(payload)
        });
        toast("New repository added successfully", "success");
      }
      setShowAddModal(false);
      loadData();
    } catch (err: any) {
      toast(err.message || "Failed to save repository settings.", "error");
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await fetchAPI(`/api/repos/${id}`, { method: "DELETE" });
      toast("Repository connection removed", "info");
      setDeletingId(null);
      loadData();
    } catch (err: any) {
      toast(err.message || "Failed to remove repository.", "error");
    }
  };

  return (
    <div className="space-y-6 animate-fade-slide-up pb-12">
      {/* Top Banner */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900 to-slate-800 border border-slate-700 shadow-lg">
        <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-10 mix-blend-overlay pointer-events-none"></div>
        <div className="p-8 relative z-10 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="p-2 bg-teal-500/10 rounded-lg border border-teal-500/20">
                <FolderKanban className="h-5 w-5 text-teal-400" />
              </div>
              <h2 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
                Repository Configurations
              </h2>
            </div>
            <p className="text-slate-400 text-sm leading-relaxed">
              Register GitHub repos, GitLab projects, Jenkins jobs, or Azure pipelines for automated error diagnosis.
            </p>
          </div>
          
          <div className="flex gap-3">
            <button
              onClick={handleOpenDiscover}
              className="bg-slate-800/80 hover:bg-slate-700 border border-slate-600 text-slate-200 font-semibold text-xs px-4 py-2.5 rounded-xl shadow-md transition-all flex items-center gap-2 shrink-0 group"
            >
              <Globe className="h-4 w-4 text-slate-400 group-hover:text-teal-400 transition-colors" />
              Discover Repos
            </button>
            <button
              onClick={handleOpenAdd}
              className="bg-gradient-to-r from-teal-500 to-emerald-500 hover:from-teal-400 hover:to-emerald-400 text-slate-950 font-bold text-xs px-4 py-2.5 rounded-xl shadow-[0_0_15px_rgba(20,184,166,0.2)] transition-all flex items-center gap-2 shrink-0"
            >
              <Plus className="h-4 w-4" />
              Add Manual
            </button>
          </div>
        </div>
      </div>

      {/* Grid of Repos */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {[1, 2, 3].map((n) => (
            <div key={n} className="h-48 rounded-2xl bg-slate-100 animate-shimmer" />
          ))}
        </div>
      ) : repos.length === 0 ? (
        <div className="py-12 glass-card rounded-2xl flex items-center justify-center border-dashed border-2 border-slate-300">
          <EmptyState
            title="Setup your first monitored repository"
            description="Connecting a repository enables the DevOps AI Hub poller to listen for failures and diagnose failed build logs."
            actionLabel="Configure New Repo"
            onAction={handleOpenAdd}
          />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {repos.map((repo) => {
            const styles = platformColors[repo.type] || platformColors.github;
            
            return (
              <div
                key={repo.id}
                className={`relative overflow-hidden rounded-2xl border ${styles.border} bg-slate-900 shadow-lg ${styles.glow} transition-all duration-300 flex flex-col justify-between group hover:-translate-y-1`}
              >
                {/* Left accent border */}
                <div className={`absolute left-0 top-0 bottom-0 w-1 ${styles.accent} opacity-80`}></div>
                
                <div className="p-6 relative z-10 pl-7">
                  <div className="flex justify-between items-start gap-4 mb-4">
                    <StatusBadge type="platform" value={repo.type} />
                    <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => handleOpenEdit(repo)}
                        className="p-1.5 bg-slate-800 text-slate-400 hover:text-white rounded-lg transition-colors border border-slate-700"
                        title="Configure"
                      >
                        <Settings2 className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setDeletingId(repo.id)}
                        className="p-1.5 bg-slate-800 text-rose-400 hover:text-white hover:bg-rose-500 rounded-lg transition-colors border border-slate-700 hover:border-rose-500"
                        title="Remove"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                  
                  <h3 className="font-extrabold text-white text-lg truncate drop-shadow-sm" title={repo.name}>
                    {repo.name}
                  </h3>
                  
                  <div className="mt-4 space-y-2">
                    {repo.url ? (
                      <p className="text-slate-400 text-xs truncate flex items-center gap-2 bg-slate-800/50 px-2.5 py-1.5 rounded-lg border border-slate-700/50" title={repo.url}>
                        <Globe className="h-3.5 w-3.5 text-slate-500 shrink-0" />
                        {repo.url}
                      </p>
                    ) : (
                      <p className="text-slate-500 text-xs italic flex items-center gap-2 bg-slate-800/50 px-2.5 py-1.5 rounded-lg border border-slate-700/50">
                        <Globe className="h-3.5 w-3.5 opacity-50" />
                        Default Server URL
                      </p>
                    )}
                    
                    {repo.extra?.pipeline_id && (
                      <p className="text-slate-400 text-xs flex items-center gap-2 font-medium bg-slate-800/50 px-2.5 py-1.5 rounded-lg border border-slate-700/50">
                        <Hash className="h-3.5 w-3.5 text-slate-500" />
                        Pipeline ID: <span className="font-mono text-teal-400 font-bold ml-1">{repo.extra.pipeline_id}</span>
                      </p>
                    )}
                  </div>
                </div>

                {/* Action Footer */}
                <div className="px-6 py-4 bg-slate-950/80 border-t border-slate-800 flex justify-between items-center relative z-10 pl-7">
                  {deletingId === repo.id ? (
                    <div className="flex items-center justify-between w-full animate-fade-slide-up">
                      <span className="text-xs text-rose-400 font-bold flex items-center gap-1.5">
                        <Trash2 className="h-3.5 w-3.5" /> Remove?
                      </span>
                      <div className="flex gap-2">
                        <button
                          onClick={() => setDeletingId(null)}
                          className="text-slate-300 bg-slate-800 hover:bg-slate-700 font-semibold text-xs px-3 py-1.5 rounded-lg transition"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={() => handleDelete(repo.id)}
                          className="text-white bg-rose-600 hover:bg-rose-500 shadow-[0_0_10px_rgba(225,29,72,0.4)] font-bold text-xs px-3 py-1.5 rounded-lg transition"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center justify-between w-full">
                      <span className="text-[10px] uppercase tracking-widest font-bold flex items-center gap-1.5">
                        {repo.credential_id ? (
                          <span className="flex items-center gap-1.5 text-emerald-400">
                            <Lock className="h-3 w-3" /> Secure Auth
                          </span>
                        ) : (
                          <span className="flex items-center gap-1.5 text-slate-500">
                            <Globe className="h-3 w-3" /> Public Access
                          </span>
                        )}
                      </span>
                      <span className="flex h-2 w-2 relative">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-teal-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-teal-500"></span>
                      </span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Add/Edit Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-slate-950/60 backdrop-blur-md flex items-center justify-center p-4 z-50 animate-fade-slide-up">
          <div className="bg-slate-900 rounded-2xl border border-slate-700 max-w-md w-full shadow-2xl overflow-hidden relative">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-teal-500 to-emerald-400"></div>
            
            <div className="px-6 py-5 border-b border-slate-800 flex justify-between items-center bg-slate-900">
              <h3 className="font-bold text-white text-lg flex items-center gap-2">
                <Settings2 className="h-5 w-5 text-teal-400" />
                {editingRepo ? "Update Monitor" : "New Monitor"}
              </h3>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-slate-400 hover:text-white transition p-1.5 hover:bg-slate-800 rounded-lg"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleSave} className="p-6 space-y-5">
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2">Platform Type</label>
                <select
                  value={type}
                  onChange={(e) => setType(e.target.value as any)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-3 text-sm font-medium text-white focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500 transition-all shadow-inner"
                  disabled={!!editingRepo}
                >
                  <option value="github">GitHub Actions</option>
                  <option value="gitlab">GitLab Pipelines</option>
                  <option value="jenkins">Jenkins Builds</option>
                  <option value="azure">Azure DevOps</option>
                </select>
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2">
                  {type === "github" ? "Repository Identifier (owner/repo)" :
                   type === "gitlab" ? "Project ID / URL Encoded Path" :
                   type === "jenkins" ? "Job Name" : "Project Name"}
                </label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={type === "github" ? "google/generative-ai" : "123456"}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-3 text-sm font-medium text-white placeholder:text-slate-600 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500 transition-all shadow-inner"
                />
              </div>

              {type !== "github" && (
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2">Target Platform base URL</label>
                  <input
                    type="url"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder={type === "gitlab" ? "https://gitlab.com" : "https://jenkins.mycompany.com"}
                    className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-3 text-sm font-medium text-white placeholder:text-slate-600 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500 transition-all shadow-inner"
                  />
                </div>
              )}

              {type === "azure" && (
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2">Pipeline ID</label>
                  <input
                    type="number"
                    required
                    value={extraPipelineId}
                    onChange={(e) => setExtraPipelineId(e.target.value)}
                    placeholder="42"
                    className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-3 text-sm font-medium text-white placeholder:text-slate-600 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500 transition-all shadow-inner"
                  />
                </div>
              )}

              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2">Credential (Optional)</label>
                <select
                  value={credentialId}
                  onChange={(e) => setCredentialId(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-3 text-sm font-medium text-slate-300 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500 transition-all shadow-inner"
                >
                  <option value="" className="text-slate-500">Leave blank for public access</option>
                  {credentials.filter(c => c.platform === type).map(c => (
                    <option key={c.id} value={c.id} className="text-white">{c.label} ({c.token_hint})</option>
                  ))}
                </select>
              </div>

              <div className="pt-6 border-t border-slate-800 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-5 py-2.5 border border-slate-600 hover:bg-slate-800 text-slate-300 font-bold text-sm rounded-xl transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2.5 bg-gradient-to-r from-teal-500 to-emerald-500 hover:from-teal-400 hover:to-emerald-400 text-slate-950 font-bold text-sm rounded-xl shadow-[0_0_15px_rgba(20,184,166,0.3)] transition-all"
                >
                  Save Configuration
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Discover Modal */}
      {showDiscoverModal && (
        <div className="fixed inset-0 bg-slate-950/60 backdrop-blur-md flex items-center justify-center p-4 z-50 animate-fade-slide-up">
          <div className="bg-slate-900 rounded-2xl border border-slate-700 max-w-2xl w-full shadow-2xl overflow-hidden flex flex-col max-h-[85vh] relative">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-indigo-500 to-purple-500"></div>

            <div className="px-6 py-5 border-b border-slate-800 flex justify-between items-center bg-slate-900 shrink-0">
              <h3 className="font-bold text-white text-lg flex items-center gap-2">
                <Globe className="h-5 w-5 text-indigo-400" />
                Discover Repositories
              </h3>
              <button
                onClick={() => setShowDiscoverModal(false)}
                className="text-slate-400 hover:text-white transition p-1.5 hover:bg-slate-800 rounded-lg"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="p-6 shrink-0 flex flex-col gap-5 border-b border-slate-800 bg-slate-900">
              <div className="flex gap-4">
                <div className="flex-1">
                  <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2">Platform</label>
                  <select
                    value={type}
                    onChange={(e) => {
                      setType(e.target.value as any);
                      setCredentialId("");
                      setDiscoveredRepos([]);
                    }}
                    className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-3 text-sm font-medium text-white focus:outline-none focus:border-indigo-500 transition-all shadow-inner"
                  >
                    <option value="github">GitHub</option>
                    <option value="gitlab">GitLab</option>
                    <option value="jenkins">Jenkins</option>
                    <option value="azure">Azure DevOps</option>
                  </select>
                </div>
                <div className="flex-1">
                  <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2">Scan Credential</label>
                  <select
                    value={credentialId}
                    onChange={(e) => setCredentialId(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-3 text-sm font-medium text-white focus:outline-none focus:border-indigo-500 transition-all shadow-inner"
                  >
                    <option value="" disabled className="text-slate-500">Select auth token</option>
                    {credentials.filter(c => c.platform === type).map(c => (
                      <option key={c.id} value={c.id}>{c.label}</option>
                    ))}
                  </select>
                </div>
              </div>
              <button
                onClick={handleDiscover}
                disabled={discoverLoading || !credentialId}
                className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-bold text-sm px-5 py-3 rounded-xl transition-all self-end shadow-lg flex items-center gap-2"
              >
                {discoverLoading ? (
                  <span className="flex items-center gap-2 animate-pulse">
                    <Activity className="h-4 w-4 animate-spin" /> Scanning...
                  </span>
                ) : (
                  <>Scan Platform <ArrowRight className="h-4 w-4" /></>
                )}
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 bg-slate-950 shadow-inner">
              {discoverLoading ? (
                <div className="flex justify-center items-center py-16">
                  <div className="relative">
                    <div className="absolute inset-0 bg-indigo-500 blur-xl opacity-20 rounded-full animate-pulse-ring"></div>
                    <Globe className="h-10 w-10 text-indigo-500 animate-pulse relative z-10" />
                  </div>
                </div>
              ) : discoveredRepos.length === 0 ? (
                <div className="text-center py-16 flex flex-col items-center gap-4">
                  <div className="p-4 bg-slate-900 rounded-full border border-slate-800">
                    <Layers className="h-8 w-8 text-slate-600" />
                  </div>
                  <p className="text-slate-400 text-sm font-medium">Select a credential and scan to find repositories.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="flex justify-between items-center mb-4">
                    <span className="text-xs font-bold text-slate-400 uppercase tracking-widest">{discoveredRepos.length} Repos Found</span>
                    <button
                      onClick={() => {
                        if (selectedDiscoverNames.size === discoveredRepos.filter(r => !r.already_added).length) {
                          setSelectedDiscoverNames(new Set());
                        } else {
                          setSelectedDiscoverNames(new Set(discoveredRepos.filter(r => !r.already_added).map(r => r.name)));
                        }
                      }}
                      className="text-indigo-400 hover:text-indigo-300 text-xs font-bold bg-indigo-500/10 px-3 py-1.5 rounded-lg border border-indigo-500/20 transition-colors"
                    >
                      Select All Available
                    </button>
                  </div>
                  {discoveredRepos.map((r, i) => (
                    <label key={i} className={`flex items-start gap-4 p-4 rounded-xl border ${r.already_added ? 'bg-slate-900 border-slate-800 opacity-50 cursor-not-allowed' : 'bg-slate-900 border-slate-700 hover:border-indigo-500 hover:shadow-[0_0_15px_rgba(99,102,241,0.15)] cursor-pointer'} transition-all`}>
                      <input
                        type="checkbox"
                        checked={selectedDiscoverNames.has(r.name) || r.already_added}
                        disabled={r.already_added}
                        onChange={(e) => {
                          const newSet = new Set(selectedDiscoverNames);
                          if (e.target.checked) newSet.add(r.name);
                          else newSet.delete(r.name);
                          setSelectedDiscoverNames(newSet);
                        }}
                        className="mt-1 shrink-0 accent-indigo-500 rounded bg-slate-800 border-slate-600 h-4 w-4 cursor-pointer"
                      />
                      <div className="flex-1 min-w-0">
                        <p className={`text-sm font-bold truncate ${r.already_added ? 'text-slate-500' : 'text-slate-200'}`}>{r.name}</p>
                        {r.url && <p className="text-xs text-slate-500 truncate mt-1 font-mono">{r.url}</p>}
                        {r.already_added && <p className="text-[10px] text-teal-500 font-bold mt-2 uppercase tracking-widest flex items-center gap-1"><Check className="h-3 w-3" /> Already imported</p>}
                      </div>
                    </label>
                  ))}
                </div>
              )}
            </div>

            <div className="p-5 border-t border-slate-800 bg-slate-900 shrink-0 flex justify-end gap-3">
              <button
                onClick={() => setShowDiscoverModal(false)}
                className="px-5 py-2.5 border border-slate-600 hover:bg-slate-800 text-slate-300 font-bold text-sm rounded-xl transition-colors"
              >
                Close
              </button>
              <button
                onClick={handleBulkImport}
                disabled={selectedDiscoverNames.size === 0}
                className="px-5 py-2.5 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 disabled:opacity-50 text-white font-bold text-sm rounded-xl shadow-[0_0_15px_rgba(99,102,241,0.3)] transition-all flex items-center gap-2"
              >
                Import {selectedDiscoverNames.size} Repos
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Ensure ArrowRight is available (added to lucide-react imports above)
import { ArrowRight, Check } from "lucide-react";
