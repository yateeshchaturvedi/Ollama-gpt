"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import Cookies from "js-cookie";
import { fetchAPI } from "@/lib/api";
import {
  LayoutDashboard,
  GitFork,
  FileText,
  Settings,
  Cpu,
  Terminal,
  Activity,
  LogOut,
  Users,
  UserCircle
} from "lucide-react";

// Custom SVG Brand Icons
const GithubIcon = ({ className }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
    <path d="M9 18c-4.51 2-5-2-7-2" />
  </svg>
);

const GitlabIcon = ({ className }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="m22 13.29-3.33-10a.42.42 0 0 0-.14-.18.38.38 0 0 0-.22-.1.39.39 0 0 0-.23.07.42.42 0 0 0-.14.18l-2.26 6.67H8.32L6.06 3.26a.42.42 0 0 0-.14-.18.38.38 0 0 0-.22-.1.39.39 0 0 0-.23.07.42.42 0 0 0-.14.18L2 13.29a.74.74 0 0 0 .27.83L12 21l9.69-6.88a.71.71 0 0 0 .31-.83Z" />
  </svg>
);

function parseJwt(token: string) {
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
      window.atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    return JSON.parse(jsonPayload);
  } catch (e) {
    return null;
  }
}

export const Sidebar: React.FC = () => {
  const pathname = usePathname();
  const router = useRouter();

  const [userProfile, setUserProfile] = useState<{ username: string; role: string } | null>(null);
  const [activeModel, setActiveModel] = useState("Gemini 1.5 Pro");

  const loadActiveModel = async () => {
    try {
      const cfg = await fetchAPI("/api/config");
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
      console.error("Failed to load active model:", err);
    }
  };

  useEffect(() => {
    const token = Cookies.get("access_token");
    if (token) {
      const payload = parseJwt(token);
      if (payload) {
        setUserProfile({ username: payload.sub, role: payload.role });
      }
    }
    loadActiveModel();
  }, [pathname]);

  const handleLogout = async () => {
    try {
      const refreshToken = Cookies.get("refresh_token");
      if (refreshToken) {
        await fetchAPI("/api/auth/logout", {
          method: "POST",
          body: JSON.stringify({ refresh_token: refreshToken }),
        }).catch(() => {});
      }
    } finally {
      Cookies.remove("access_token", { path: '/' });
      Cookies.remove("refresh_token", { path: '/' });
      router.push("/login");
    }
  };

  const isActive = (href: string) => {
    if (href === "/") return pathname === href;
    return pathname.startsWith(href);
  };

  const navItemClass = (href: string) => {
    const active = isActive(href);
    return `flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-300 relative overflow-hidden ${
      active
        ? "bg-teal-500/10 text-teal-400 shadow-[inset_2px_0_0_0_rgba(45,212,191,1)]"
        : "text-slate-400 hover:bg-slate-800/50 hover:text-slate-200"
    }`;
  };

  const isAdminOrOwner = userProfile?.role === "owner" || userProfile?.role === "admin";

  return (
    <aside className="w-64 bg-slate-950 border-r border-slate-800 flex flex-col shrink-0 animate-fade-slide-up h-screen sticky top-0 z-20">
      {/* Brand Header */}
      <div className="h-16 border-b border-slate-800/50 flex items-center px-6 relative overflow-hidden bg-slate-900/50 backdrop-blur-xl">
        <div className="absolute top-0 left-0 w-full h-full bg-teal-500/5 blur-2xl"></div>
        <Link href="/" className="font-bold text-lg tracking-tight flex items-center gap-3 relative z-10">
          <div className="relative">
            <div className="absolute inset-0 bg-teal-400 blur-md opacity-40 rounded-xl animate-pulse-ring"></div>
            <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-teal-500 to-emerald-400 flex items-center justify-center text-white shadow-lg shadow-teal-900/50 relative z-10 border border-teal-400/20">
              <Cpu className="h-5 w-5" />
            </div>
          </div>
          <span className="bg-gradient-to-r from-teal-400 to-emerald-300 bg-clip-text text-transparent font-extrabold tracking-tight">
            DevOps AI Hub
          </span>
        </Link>
      </div>

      {/* Main Nav */}
      <nav className="flex-1 p-4 space-y-1.5 overflow-y-auto">
        <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest px-4 mb-3 mt-2 flex items-center gap-2">
          Overview
          <div className="h-px flex-1 bg-slate-800/50"></div>
        </div>

        <Link href="/" className={navItemClass("/")}>
          <LayoutDashboard className={`h-4.5 w-4.5 ${isActive("/") ? "text-teal-400" : ""}`} />
          <span>Dashboard</span>
        </Link>

        {isAdminOrOwner && (
          <Link href="/repos" className={navItemClass("/repos")}>
            <GitFork className={`h-4.5 w-4.5 ${isActive("/repos") ? "text-teal-400" : ""}`} />
            <span>Repositories</span>
          </Link>
        )}

        <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest px-4 mb-3 mt-8 flex items-center gap-2">
          Tool Windows
          <div className="h-px flex-1 bg-slate-800/50"></div>
        </div>

        <Link href="/github" className={navItemClass("/github")}>
          <GithubIcon className={`h-4.5 w-4.5 ${isActive("/github") ? "text-teal-400" : ""}`} />
          <span>GitHub Actions</span>
        </Link>

        <Link href="/gitlab" className={navItemClass("/gitlab")}>
          <GitlabIcon className={`h-4.5 w-4.5 ${isActive("/gitlab") ? "text-teal-400" : ""}`} />
          <span>GitLab CI</span>
        </Link>

        <Link href="/jenkins" className={navItemClass("/jenkins")}>
          <Terminal className={`h-4.5 w-4.5 ${isActive("/jenkins") ? "text-teal-400" : ""}`} />
          <span>Jenkins Builds</span>
        </Link>

        <Link href="/azure" className={navItemClass("/azure")}>
          <Activity className={`h-4.5 w-4.5 ${isActive("/azure") ? "text-teal-400" : ""}`} />
          <span>Azure DevOps</span>
        </Link>

        <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest px-4 mb-3 mt-8 flex items-center gap-2">
          System
          <div className="h-px flex-1 bg-slate-800/50"></div>
        </div>

        <Link href="/logs" className={navItemClass("/logs")}>
          <FileText className={`h-4.5 w-4.5 ${isActive("/logs") ? "text-teal-400" : ""}`} />
          <span>Audit Logs</span>
        </Link>

        {isAdminOrOwner && (
          <Link href="/team" className={navItemClass("/team")}>
            <Users className={`h-4.5 w-4.5 ${isActive("/team") ? "text-teal-400" : ""}`} />
            <span>Team Members</span>
          </Link>
        )}

        {isAdminOrOwner && (
          <Link href="/settings" className={navItemClass("/settings")}>
            <Settings className={`h-4.5 w-4.5 ${isActive("/settings") ? "text-teal-400" : ""}`} />
            <span>Settings</span>
          </Link>
        )}

        {/* Profile link — visible to all */}
        <Link href="/profile" className={navItemClass("/profile")}>
          <UserCircle className={`h-4.5 w-4.5 ${isActive("/profile") ? "text-teal-400" : ""}`} />
          <span>My Profile</span>
        </Link>
      </nav>

      {/* Footer Info Box */}
      <div className="p-4 border-t border-slate-800/50 bg-slate-900/50 flex flex-col gap-3 relative">
        <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-t from-slate-950 to-transparent pointer-events-none opacity-50"></div>
        
        {userProfile && (
          <Link href="/profile" className="flex items-center justify-between bg-slate-800/40 border border-slate-700/50 p-2.5 rounded-xl shadow-lg hover:border-teal-500/30 hover:bg-slate-800/60 transition-all group relative z-10">
            <div className="flex items-center gap-3 overflow-hidden">
              <div className="relative">
                <div className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 bg-emerald-500 rounded-full border-2 border-slate-900 z-10"></div>
                <div className="h-9 w-9 rounded-full bg-gradient-to-tr from-slate-600 to-slate-400 flex items-center justify-center text-white shrink-0 font-bold text-sm shadow-md border border-slate-500/30 group-hover:from-teal-500 group-hover:to-emerald-400 transition-all">
                  {userProfile.username.charAt(0).toUpperCase()}
                </div>
              </div>
              <div className="flex flex-col min-w-0">
                <span className="text-sm font-bold text-slate-200 truncate group-hover:text-white transition-colors">{userProfile.username}</span>
                <span className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider">{userProfile.role}</span>
              </div>
            </div>
            <button
              onClick={(e) => { e.preventDefault(); handleLogout(); }}
              className="p-2 text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-colors"
              title="Logout"
            >
              <LogOut className="h-4.5 w-4.5" />
            </button>
          </Link>
        )}
        
        <div className="flex items-center justify-between bg-teal-950/30 border border-teal-900/50 rounded-lg p-2.5 relative z-10">
          <span className="text-slate-400 text-[10px] font-bold uppercase tracking-wider">AI Engine</span>
          <span className="font-bold text-teal-300 text-xs flex items-center gap-1.5 bg-teal-500/10 px-2 py-0.5 rounded-md border border-teal-500/20">
            <span className="h-1.5 w-1.5 rounded-full bg-teal-400 animate-pulse shadow-[0_0_5px_rgba(45,212,191,0.5)]"></span>
            {activeModel}
          </span>
        </div>
      </div>
    </aside>
  );
};
