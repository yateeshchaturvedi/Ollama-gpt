"use client";

import React, { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import Cookies from "js-cookie";
import { Wifi, WifiOff, ShieldAlert, Shield, Eye } from "lucide-react";
import { fetchAPI } from "@/lib/api";

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

export const Header: React.FC = () => {
  const pathname = usePathname();
  const [online, setOnline] = useState<boolean | null>(null);
  const [role, setRole] = useState<string>("user");

  useEffect(() => {
    const token = Cookies.get("access_token");
    if (token) {
      const payload = parseJwt(token);
      if (payload && payload.role) {
        setRole(payload.role);
      }
    }
  }, [pathname]);

  // Poll repos endpoint to test connectivity
  const checkStatus = async () => {
    try {
      await fetchAPI("/api/repos");
      setOnline(true);
    } catch (err) {
      setOnline(false);
    }
  };

  useEffect(() => {
    checkStatus();
    const interval = setInterval(checkStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  // Format header title based on route path
  const getBreadcrumb = () => {
    if (pathname === "/") return "Dashboard Overview";
    const section = pathname.split("/")[1];
    if (!section) return "DevOps AI Hub";
    
    // Map path to friendly names
    const maps: Record<string, string> = {
      repos: "Repository Management",
      github: "GitHub Action Workflows",
      gitlab: "GitLab Pipelines",
      jenkins: "Jenkins Job Builds",
      azure: "Azure Pipelines",
      logs: "System Audit Logs",
      settings: "Engine Configurations",
    };
    
    return maps[section] || section.charAt(0).toUpperCase() + section.slice(1);
  };

  const getRoleBadge = () => {
    switch (role) {
      case "owner":
      case "admin":
        return (
          <div className="flex items-center gap-1.5 bg-rose-50 border border-rose-200/60 px-3 py-1.5 rounded-full shadow-sm">
            <ShieldAlert className="h-3.5 w-3.5 text-rose-600 drop-shadow-[0_0_2px_rgba(225,29,72,0.4)]" />
            <span className="font-bold text-rose-700 text-xs">Admin Portal</span>
          </div>
        );
      case "analyst":
        return (
          <div className="flex items-center gap-1.5 bg-blue-50 border border-blue-200/60 px-3 py-1.5 rounded-full shadow-sm">
            <Shield className="h-3.5 w-3.5 text-blue-600 drop-shadow-[0_0_2px_rgba(37,99,235,0.4)]" />
            <span className="font-bold text-blue-700 text-xs">Analyst Portal</span>
          </div>
        );
      case "viewer":
      default:
        return (
          <div className="flex items-center gap-1.5 bg-slate-100 border border-slate-200/60 px-3 py-1.5 rounded-full shadow-sm">
            <Eye className="h-3.5 w-3.5 text-slate-500 drop-shadow-[0_0_2px_rgba(100,116,139,0.4)]" />
            <span className="font-bold text-slate-600 text-xs">Viewer Portal</span>
          </div>
        );
    }
  };

  return (
    <header className="h-16 glass-card border-b-0 border-l-0 flex items-center justify-between px-8 shrink-0 sticky top-0 z-10 transition-all duration-300">
      <div className="flex items-center gap-4">
        <h1 className="font-extrabold text-slate-800 text-sm tracking-tight md:text-base animate-fade-slide-up bg-gradient-to-r from-slate-900 to-slate-600 bg-clip-text text-transparent">
          {getBreadcrumb()}
        </h1>
        <span className="text-slate-300 text-xs font-normal">|</span>
        
        {online === null && (
          <span className="text-[10px] font-bold text-slate-500 bg-slate-100 border border-slate-200 px-3 py-1 rounded-full flex items-center gap-2 shadow-sm">
            <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-pulse"></span>
            Checking connection...
          </span>
        )}

        {online === true && (
          <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200/60 px-3 py-1 rounded-full flex items-center gap-2 shadow-sm relative overflow-hidden group">
            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-emerald-400/10 to-transparent -translate-x-full group-hover:animate-[shimmer_1.5s_infinite]"></div>
            <Wifi className="h-3.5 w-3.5 text-emerald-500 animate-pulse drop-shadow-[0_0_2px_rgba(16,185,129,0.5)]" />
            API Connected
          </span>
        )}

        {online === false && (
          <span className="text-[10px] font-bold text-rose-700 bg-rose-50 border border-rose-200/60 px-3 py-1 rounded-full flex items-center gap-2 shadow-sm relative overflow-hidden">
            <div className="absolute inset-0 bg-rose-500/5 animate-pulse"></div>
            <WifiOff className="h-3.5 w-3.5 text-rose-500 drop-shadow-[0_0_2px_rgba(244,63,94,0.5)]" />
            API Offline
          </span>
        )}
      </div>

      <div className="flex items-center gap-3">
        {getRoleBadge()}
      </div>
    </header>
  );
};
