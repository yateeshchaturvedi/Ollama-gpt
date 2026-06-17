"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import Cookies from "js-cookie";
import { Cpu, Loader2, Lock, Building2, User, ArrowRight } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { useToast } from "@/components/Toast";

export default function LoginPage() {
  const router = useRouter();
  const { toast } = useToast();

  const [orgSlug, setOrgSlug] = useState("");
  const [usernameOrEmail, setUsernameOrEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      const response = await fetchAPI("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          org_slug: orgSlug,
          username_or_email: usernameOrEmail,
          password,
        }),
      });

      Cookies.set("access_token", response.access_token, { path: "/", expires: 1 });
      Cookies.set("refresh_token", response.refresh_token, { path: "/", expires: 30 });

      toast("Logged in successfully", "success");
      router.push("/");
      router.refresh();
    } catch (err: any) {
      toast(err.message || "Failed to log in", "error");
    } finally {
      setIsLoading(false);
    }
  };

  const inputClass =
    "w-full bg-slate-900/50 border border-slate-700 rounded-xl pl-11 pr-4 py-3.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500/50 focus:border-teal-400 transition-all placeholder:text-slate-500 text-slate-200 font-medium backdrop-blur-sm shadow-inner group-hover:border-slate-600";

  return (
    <div className="min-h-screen w-full bg-slate-950 flex items-center justify-center p-4 relative overflow-hidden font-sans">
      {/* Deep animated background elements */}
      <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-20 mix-blend-overlay pointer-events-none z-0"></div>
      
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-teal-600/20 rounded-full blur-[120px] pointer-events-none animate-float z-0" style={{ animationDelay: '0s' }} />
      <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-emerald-600/20 rounded-full blur-[120px] pointer-events-none animate-float z-0" style={{ animationDelay: '-4s' }} />
      <div className="absolute top-[40%] left-[40%] w-[30%] h-[30%] bg-indigo-600/10 rounded-full blur-[100px] pointer-events-none animate-float z-0" style={{ animationDelay: '-2s' }} />

      <div className="w-full max-w-[420px] auth-glass-dark rounded-3xl p-8 sm:p-10 relative z-10 animate-fade-slide-up">
        {/* Logo + Heading */}
        <div className="flex flex-col items-center mb-10 relative">
          <div className="absolute inset-0 bg-teal-500/20 blur-2xl rounded-full scale-150"></div>
          <div className="h-16 w-16 rounded-2xl bg-gradient-to-tr from-teal-500 to-emerald-400 flex items-center justify-center text-white shadow-xl shadow-teal-900/50 border border-teal-400/30 mb-6 relative z-10">
            <Cpu className="h-8 w-8" />
          </div>
          <h1 className="text-3xl font-extrabold text-white tracking-tight relative z-10">Welcome Back</h1>
          <p className="text-sm text-slate-400 mt-2 text-center font-medium relative z-10">
            Sign in to your DevOps AI Hub workspace.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="group">
            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2 ml-1">
              Organisation Slug
            </label>
            <div className="relative">
              <Building2 className="absolute left-4 top-1/2 -translate-y-1/2 h-4.5 w-4.5 text-slate-500 group-focus-within:text-teal-400 transition-colors" />
              <input
                id="org-slug"
                type="text"
                required
                value={orgSlug}
                onChange={(e) => setOrgSlug(e.target.value)}
                placeholder="e.g. acme-corp"
                className={inputClass}
              />
            </div>
          </div>

          <div className="group">
            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2 ml-1">
              Username or Email
            </label>
            <div className="relative">
              <User className="absolute left-4 top-1/2 -translate-y-1/2 h-4.5 w-4.5 text-slate-500 group-focus-within:text-teal-400 transition-colors" />
              <input
                id="username-or-email"
                type="text"
                required
                value={usernameOrEmail}
                onChange={(e) => setUsernameOrEmail(e.target.value)}
                placeholder="admin or admin@acme.com"
                className={inputClass}
              />
            </div>
          </div>

          <div className="group">
            <div className="flex justify-between items-center mb-2 ml-1 mr-1">
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                Password
              </label>
            </div>
            <div className="relative">
              <Lock className="absolute left-4 top-1/2 -translate-y-1/2 h-4.5 w-4.5 text-slate-500 group-focus-within:text-teal-400 transition-colors" />
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className={inputClass}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-gradient-to-r from-teal-500 to-emerald-500 hover:from-teal-400 hover:to-emerald-400 text-slate-950 font-bold rounded-xl px-4 py-3.5 mt-4 shadow-[0_0_20px_rgba(20,184,166,0.3)] transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 group relative overflow-hidden"
          >
            <div className="absolute inset-0 bg-white/20 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-700 ease-in-out"></div>
            {isLoading ? (
              <>
                <Loader2 className="h-5 w-5 animate-spin" />
                Signing in...
              </>
            ) : (
              <>
                Sign In to Workspace
                <ArrowRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
              </>
            )}
          </button>
        </form>

        <div className="mt-8 pt-6 border-t border-slate-800/60 text-center">
          <p className="text-sm text-slate-400 font-medium">
            Setting up for the first time?{" "}
            <a
              href="/admin/register"
              className="font-bold text-teal-400 hover:text-teal-300 transition-colors drop-shadow-[0_0_8px_rgba(45,212,191,0.4)]"
            >
              Create an organisation
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
