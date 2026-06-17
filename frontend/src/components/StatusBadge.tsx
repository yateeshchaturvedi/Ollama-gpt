"use client";

import React from "react";
import { CheckCircle2, XCircle, AlertCircle, PlayCircle, Ban } from "lucide-react";

type BadgeType = "platform" | "status";

interface StatusBadgeProps {
  type?: BadgeType;
  value: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ type = "status", value }) => {
  const normVal = value.toLowerCase().trim();

  if (type === "platform") {
    let styles = "bg-slate-100 text-slate-800 border-slate-200";
    let displayName = value;

    if (normVal === "github") {
      styles = "bg-slate-900/5 text-slate-800 border-slate-900/10";
      displayName = "GitHub";
    } else if (normVal === "gitlab") {
      styles = "bg-orange-50 text-orange-700 border-orange-200";
      displayName = "GitLab";
    } else if (normVal === "jenkins") {
      styles = "bg-red-50 text-red-700 border-red-200";
      displayName = "Jenkins";
    } else if (normVal === "azure" || normVal === "azure_devops") {
      styles = "bg-blue-50 text-blue-700 border-blue-200";
      displayName = "Azure DevOps";
    }

    return (
      <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${styles} uppercase tracking-wider`}>
        {displayName}
      </span>
    );
  }

  // Otherwise, handle run/build statuses
  let colorStyles = "bg-slate-50 text-slate-600 border-slate-200";
  let icon = <AlertCircle className="h-3.5 w-3.5" />;
  let label = value;

  if (["success", "passed", "complete", "completed", "succeeded"].includes(normVal)) {
    colorStyles = "bg-emerald-50 text-emerald-700 border-emerald-200";
    icon = <CheckCircle2 className="h-3.5 w-3.5" />;
    label = "Success";
  } else if (["failure", "failed", "error", "fail"].includes(normVal)) {
    colorStyles = "bg-rose-50 text-rose-700 border-rose-200";
    icon = <XCircle className="h-3.5 w-3.5" />;
    label = "Failed";
  } else if (["running", "in_progress", "progress", "building", "queued", "pending"].includes(normVal)) {
    colorStyles = "bg-amber-50 text-amber-700 border-amber-200";
    icon = <PlayCircle className="h-3.5 w-3.5 animate-spin" style={{ animationDuration: "3s" }} />;
    label = normVal === "building" ? "Building" : "Running";
  } else if (["cancelled", "canceled", "skipped", "stopped"].includes(normVal)) {
    colorStyles = "bg-slate-50 text-slate-500 border-slate-200";
    icon = <Ban className="h-3.5 w-3.5" />;
    label = "Cancelled";
  }

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold border ${colorStyles}`}>
      {icon}
      <span>{label}</span>
    </span>
  );
};
