"use client";

import React from "react";
import { FolderOpen } from "lucide-react";

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  actionLabel,
  onAction,
}) => {
  return (
    <div className="flex flex-col items-center justify-center text-center p-8 md:p-12 border border-dashed border-slate-200 rounded-2xl bg-white/50 backdrop-blur-xs max-w-md mx-auto animate-fade-slide-up">
      <div className="p-4 bg-slate-50 border border-slate-100 rounded-full text-slate-400 mb-4 shadow-xs">
        {icon || <FolderOpen className="h-8 w-8 text-slate-400" />}
      </div>
      <h3 className="text-base font-bold text-slate-800 tracking-tight">{title}</h3>
      <p className="text-slate-500 text-xs mt-1.5 max-w-xs leading-relaxed">{description}</p>
      {actionLabel && onAction && (
        <button
          onClick={onAction}
          className="mt-5 px-4 py-2 text-xs font-semibold text-white bg-teal-600 hover:bg-teal-700 active:bg-teal-800 rounded-xl transition shadow-xs hover:shadow-sm"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
};
