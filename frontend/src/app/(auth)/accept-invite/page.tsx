"use client";

import React, { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Cpu, Loader2, User, Lock, Eye, EyeOff, Mail } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { useToast } from "@/components/Toast";

function AcceptInviteForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { toast } = useToast();

  const inviteCode = searchParams.get("code") || "";

  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const passwordsMatch = confirmPassword === "" || password === confirmPassword;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      toast("Passwords do not match", "error");
      return;
    }
    if (!inviteCode) {
      toast("Invalid invite link — no code provided", "error");
      return;
    }
    setIsLoading(true);

    try {
      await fetchAPI("/api/admin/users/invites/accept", {
        method: "POST",
        body: JSON.stringify({
          invite_code: inviteCode,
          username,
          password,
          display_name: displayName || undefined,
        }),
      });

      toast("Account created successfully! You can now sign in.", "success");
      router.push("/login");
    } catch (err: any) {
      toast(err.message || "Failed to accept invite", "error");
    } finally {
      setIsLoading(false);
    }
  };

  const inputClass =
    "w-full bg-slate-50 border border-slate-200 rounded-xl pl-10 pr-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500/50 focus:border-teal-500 transition-all placeholder:text-slate-400 text-slate-800 font-medium";
  const labelClass = "block text-xs font-semibold text-slate-600 uppercase tracking-wider mb-1.5 ml-1";

  return (
    <div className="min-h-screen w-full bg-slate-50 flex items-center justify-center p-4 relative overflow-hidden">
      {/* Decorative background */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-teal-300/20 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-emerald-300/20 rounded-full blur-[120px] pointer-events-none" />

      <div className="w-full max-w-md bg-white/80 backdrop-blur-xl border border-slate-200/60 rounded-3xl shadow-xl shadow-teal-900/5 p-8 relative z-10">
        {/* Header */}
        <div className="flex flex-col items-center mb-8">
          <div className="h-14 w-14 rounded-2xl bg-gradient-to-tr from-teal-500 to-emerald-400 flex items-center justify-center text-white shadow-lg shadow-teal-500/30 mb-4">
            <Cpu className="h-7 w-7" />
          </div>
          <h1 className="text-2xl font-bold text-slate-800 tracking-tight">Accept Invitation</h1>
          <p className="text-sm text-slate-500 mt-1.5 text-center">
            Create your account to join the team on DevOps AI Hub.
          </p>
        </div>

        {!inviteCode ? (
          <div className="text-center py-8">
            <div className="w-12 h-12 bg-rose-50 border border-rose-200 rounded-full flex items-center justify-center mx-auto mb-4">
              <Mail className="h-6 w-6 text-rose-400" />
            </div>
            <h2 className="text-lg font-semibold text-slate-800 mb-2">Invalid Invite Link</h2>
            <p className="text-sm text-slate-500 mb-6">
              The invite link you followed is missing a code. Please check the email you received and try again.
            </p>
            <Link href="/login" className="text-teal-600 hover:text-teal-700 text-sm font-semibold underline">
              Back to Login
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className={labelClass}>Display Name</label>
              <div className="relative">
                <User className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <input
                  id="display-name"
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="John Doe"
                  className={inputClass}
                />
              </div>
            </div>

            <div>
              <label className={labelClass}>
                Username <span className="text-rose-500 font-bold">*</span>
              </label>
              <div className="relative">
                <User className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <input
                  id="username"
                  type="text"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="johndoe"
                  className={inputClass}
                />
              </div>
            </div>

            <div>
              <label className={labelClass}>
                Password <span className="text-rose-500 font-bold">*</span>
              </label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Min 8 characters"
                  className={inputClass.replace("pr-4", "pr-10")}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <div>
              <label className={labelClass}>
                Confirm Password <span className="text-rose-500 font-bold">*</span>
              </label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <input
                  id="confirm-password"
                  type={showConfirm ? "text" : "password"}
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Repeat password"
                  className={`${inputClass.replace("pr-4", "pr-10")} ${
                    !passwordsMatch ? "border-rose-400 focus:ring-rose-400/40 focus:border-rose-400" : ""
                  }`}
                />
                <button
                  type="button"
                  onClick={() => setShowConfirm(!showConfirm)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors"
                >
                  {showConfirm ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              {!passwordsMatch && (
                <p className="text-xs text-rose-500 mt-1.5 ml-1">Passwords don't match</p>
              )}
            </div>

            <button
              type="submit"
              disabled={isLoading || !passwordsMatch}
              className="w-full bg-teal-600 hover:bg-teal-700 text-white font-medium rounded-xl px-4 py-3 mt-2 shadow-md shadow-teal-500/20 transition-all disabled:opacity-70 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-5 w-5 animate-spin" />
                  Creating Account...
                </>
              ) : (
                "Accept & Create Account"
              )}
            </button>
          </form>
        )}

        <div className="mt-8 pt-6 border-t border-slate-100 text-center">
          <p className="text-sm text-slate-500">
            Already have an account?{" "}
            <Link href="/login" className="font-semibold text-teal-600 hover:text-teal-700 hover:underline transition-colors">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

export default function AcceptInvitePage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-slate-50 flex items-center justify-center">
          <Loader2 className="h-8 w-8 text-teal-600 animate-spin" />
        </div>
      }
    >
      <AcceptInviteForm />
    </Suspense>
  );
}
