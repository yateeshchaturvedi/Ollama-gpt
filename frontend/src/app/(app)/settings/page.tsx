"use client";

import { useEffect, useState } from "react";
import { fetchAPI } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { 
  Settings2, 
  Save, 
  Cpu, 
  ShieldCheck, 
  HelpCircle,
  CheckCircle,
  RefreshCw
} from "lucide-react";

interface Config {
  llm_provider: string;
  google_model: string;
  google_api_key: string;
  max_tool_steps: number;
  max_history: number;
  dangerous_actions_require_confirmation: boolean;
}

interface ModelOption {
  id: string;
  name: string;
}

export default function SettingsPage() {
  const [config, setConfig] = useState<Config | null>(null);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  // Form fields
  const [llmProvider, setLlmProvider] = useState("gemini");
  const [googleModel, setGoogleModel] = useState("gemini-1.5-pro");
  const [googleApiKey, setGoogleApiKey] = useState("");
  const [maxToolSteps, setMaxToolSteps] = useState(5);
  const [maxHistory, setMaxHistory] = useState(12);
  const [reqConfirmation, setReqConfirmation] = useState(true);

  const { toast } = useToast();

  const loadData = async () => {
    setLoading(true);
    try {
      const [cfg, mdlist] = await Promise.all([
        fetchAPI("/api/config"),
        fetchAPI("/api/config/models")
      ]);
      setConfig(cfg);
      setModels(mdlist);
      
      // Init form fields
      setLlmProvider(cfg.llm_provider);
      setGoogleModel(cfg.google_model);
      setGoogleApiKey(cfg.google_api_key);
      setMaxToolSteps(cfg.max_tool_steps);
      setMaxHistory(cfg.max_history);
      setReqConfirmation(cfg.dangerous_actions_require_confirmation);
    } catch (err: any) {
      toast(err.message || "Failed to load configurations.", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);

    const payload = {
      llm_provider: llmProvider,
      google_model: googleModel,
      google_api_key: googleApiKey,
      max_tool_steps: maxToolSteps,
      max_history: maxHistory,
      dangerous_actions_require_confirmation: reqConfirmation
    };

    try {
      const res = await fetchAPI("/api/config", {
        method: "POST",
        body: JSON.stringify(payload)
      });
      toast(res.message || "Settings updated and saved to .env file!", "success");
      
      // Reload config to get masked key if updated
      const updatedCfg = await fetchAPI("/api/config");
      setConfig(updatedCfg);
      setGoogleApiKey(updatedCfg.google_api_key);
    } catch (err: any) {
      toast(err.message || "Failed to save settings.", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleTestConnection = async () => {
    setTesting(true);
    try {
      // Pinging the repos API endpoint to verify connectivity
      await fetchAPI("/api/repos");
      toast("API connection test successful. Service is healthy.", "success");
    } catch (err: any) {
      toast("API connection test failed. Check server status.", "error");
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6 max-w-2xl animate-pulse">
        <div className="h-6 w-40 bg-slate-200 rounded-lg" />
        <div className="h-4 w-96 bg-slate-200 rounded-lg" />
        <div className="h-96 bg-white border border-slate-250 rounded-2xl mt-6" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl space-y-6 animate-fade-slide-up">
      {/* Header card */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center bg-white border border-slate-200 p-6 rounded-2xl gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800 tracking-tight flex items-center gap-2">
            <Settings2 className="h-5 w-5 text-teal-600" />
            Engine Configurations
          </h2>
          <p className="text-slate-500 text-xs mt-1 leading-relaxed">
            Configure default LLM providers, credentials API keys, safety thresholds, and agent parameters.
          </p>
        </div>

        <button
          onClick={handleTestConnection}
          disabled={testing}
          className="text-slate-700 bg-white border border-slate-350 hover:bg-slate-50 font-semibold text-xs px-4 py-2.5 rounded-xl shadow-xs transition duration-150 flex items-center gap-1.5 shrink-0"
        >
          {testing ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle className="h-3.5 w-3.5 text-teal-600" />}
          Test Server Ping
        </button>
      </div>

      {/* Main config form */}
      <form onSubmit={handleSave} className="bg-white border border-slate-200 rounded-2xl shadow-xs overflow-hidden">
        <div className="p-6 space-y-6">
          
          {/* LLM Provider Selection */}
          <div className="border-b border-slate-100 pb-5">
            <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <Cpu className="h-4 w-4 text-teal-600" />
              LLM Provider Client
            </label>
            <select
              value={llmProvider}
              onChange={(e) => setLlmProvider(e.target.value)}
              className="w-full border border-slate-250 rounded-xl px-3.5 py-2 text-xs font-semibold focus:outline-none focus:border-teal-500 bg-white shadow-xs"
            >
              <option value="gemini">Google Gemini (Active)</option>
              <option value="openai">OpenAI (stub)</option>
              <option value="anthropic">Anthropic Claude (stub)</option>
            </select>
            <p className="text-[10px] text-slate-400 mt-2 leading-relaxed">
              Changing the client model provider updates active background threads instantly.
            </p>
          </div>

          {/* Model specific configuration */}
          {llmProvider === "gemini" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 border-b border-slate-100 pb-5">
              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">Gemini Model Type</label>
                <select
                  value={googleModel}
                  onChange={(e) => setGoogleModel(e.target.value)}
                  className="w-full border border-slate-250 rounded-xl px-3.5 py-2 text-xs font-semibold focus:outline-none focus:border-teal-500 bg-white shadow-xs"
                >
                  {models.map((opt) => (
                    <option key={opt.id} value={opt.id}>{opt.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">Google AI APIs Key</label>
                <input
                  type="password"
                  value={googleApiKey}
                  onChange={(e) => setGoogleApiKey(e.target.value)}
                  placeholder="Insert API key..."
                  className="w-full border border-slate-250 rounded-xl px-3.5 py-2 text-xs focus:outline-none focus:border-teal-500 bg-white font-mono shadow-xs"
                />
              </div>
            </div>
          )}

          {/* Step limitations */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 border-b border-slate-100 pb-5">
            <div>
              <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-1">
                Max Tool Steps 
                <span className="text-slate-350 cursor-help" title="Max tool calls allowed in a single turn."><HelpCircle className="h-3 w-3" /></span>
              </label>
              <input
                type="number"
                min={1}
                max={20}
                value={maxToolSteps}
                onChange={(e) => setMaxToolSteps(parseInt(e.target.value, 10) || 5)}
                className="w-full border border-slate-250 rounded-xl px-3.5 py-2 text-xs focus:outline-none focus:border-teal-500 bg-white shadow-xs"
              />
              <p className="text-[10px] text-slate-400 mt-1.5 leading-relaxed">Limits recursive agent executions to prevent infinite run loops.</p>
            </div>

            <div>
              <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-1">
                Max Conversation History
                <span className="text-slate-350 cursor-help" title="Number of turns kept in active memory."><HelpCircle className="h-3 w-3" /></span>
              </label>
              <input
                type="number"
                min={2}
                max={100}
                value={maxHistory}
                onChange={(e) => setMaxHistory(parseInt(e.target.value, 10) || 12)}
                className="w-full border border-slate-250 rounded-xl px-3.5 py-2 text-xs focus:outline-none focus:border-teal-500 bg-white shadow-xs"
              />
              <p className="text-[10px] text-slate-400 mt-1.5 leading-relaxed">Safety window threshold size before trimming token messages.</p>
            </div>
          </div>

          {/* Safety Confirmations */}
          <div className="pt-2">
            <div className="flex items-start gap-3">
              <input
                type="checkbox"
                id="req-confirm"
                checked={reqConfirmation}
                onChange={(e) => setReqConfirmation(e.target.checked)}
                className="h-4.5 w-4.5 rounded-lg border-slate-300 text-teal-600 focus:ring-teal-500 mt-0.5"
              />
              <div>
                <label htmlFor="req-confirm" className="text-xs font-bold text-slate-700 select-none cursor-pointer flex items-center gap-1">
                  <ShieldCheck className="h-4 w-4 text-teal-600" />
                  Require manual safety confirmation tokens
                </label>
                <p className="text-[10px] text-slate-400 mt-1 leading-relaxed">
                  Triggers explicit authorization prompt dialogs for dangerous commands (e.g. file overwrites or command terminal shells).
                </p>
              </div>
            </div>
          </div>

        </div>

        {/* Footer save block */}
        <div className="px-6 py-4 bg-slate-50/50 border-t border-slate-200 flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="bg-teal-600 hover:bg-teal-700 disabled:bg-teal-500 text-white font-semibold text-xs px-4 py-2.5 rounded-xl shadow-xs transition duration-150 flex items-center gap-1.5"
          >
            {saving ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
            {saving ? "Saving Changes..." : "Save Settings"}
          </button>
        </div>
      </form>
    </div>
  );
}
