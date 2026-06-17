"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Mail, Loader2, ArrowRight } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { useToast } from "@/components/Toast";

function VerifyEmailForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { toast } = useToast();
  
  const [token, setToken] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  // Auto-fill from query param
  useEffect(() => {
    const queryToken = searchParams.get("token");
    if (queryToken) {
      setToken(queryToken);
    }
  }, [searchParams]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      await fetchAPI("/api/auth/verify-email", {
        method: "POST",
        body: JSON.stringify({ token }),
      });

      toast("Email verified successfully! You can now log in.", "success");
      router.push("/login");
    } catch (err: any) {
      toast(err.message || "Invalid or expired token", "error");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md bg-white/80 backdrop-blur-xl border border-slate-200/60 rounded-3xl shadow-xl shadow-teal-900/5 p-8 relative z-10">
      <div className="flex flex-col items-center mb-8">
        <div className="h-16 w-16 rounded-full bg-teal-50 flex items-center justify-center text-teal-600 mb-4 border border-teal-100">
          <Mail className="h-7 w-7" />
        </div>
        <h1 className="text-2xl font-bold text-slate-800 tracking-tight text-center">Verify Your Email</h1>
        <p className="text-sm text-slate-500 mt-2 text-center leading-relaxed">
          We've created your workspace. Please enter the verification code to activate your account.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wider mb-1.5 ml-1">
            Verification Token
          </label>
          <input
            type="text"
            required
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Paste your token here..."
            className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500/50 focus:border-teal-500 transition-all placeholder:text-slate-400 text-slate-800 font-mono tracking-wider"
          />
        </div>

        <button
          type="submit"
          disabled={isLoading || !token}
          className="w-full bg-teal-600 hover:bg-teal-700 text-white font-medium rounded-xl px-4 py-3 mt-2 shadow-md shadow-teal-500/20 transition-all disabled:opacity-70 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {isLoading ? (
            <>
              <Loader2 className="h-5 w-5 animate-spin" />
              Verifying...
            </>
          ) : (
            <>
              Verify Account <ArrowRight className="h-4 w-4" />
            </>
          )}
        </button>
      </form>

      <div className="mt-8 pt-6 border-t border-slate-100 text-center">
        <Link href="/login" className="text-sm font-medium text-slate-500 hover:text-slate-800 transition-colors">
          Back to Login
        </Link>
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4 relative overflow-hidden">
      {/* Decorative background elements */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-teal-300/20 rounded-full blur-[120px] pointer-events-none"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-emerald-300/20 rounded-full blur-[120px] pointer-events-none"></div>

      <Suspense fallback={<div className="w-full max-w-md bg-white p-8 rounded-3xl shadow-xl flex justify-center"><Loader2 className="animate-spin text-teal-600 w-8 h-8"/></div>}>
        <VerifyEmailForm />
      </Suspense>
    </div>
  );
}
