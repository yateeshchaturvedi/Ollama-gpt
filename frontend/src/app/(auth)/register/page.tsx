"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Cpu, Loader2, User, Mail, Lock, Building2, Hash, Eye, EyeOff, Check, ArrowRight } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { useToast } from "@/components/Toast";

function slugify(text: string) {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 50);
}

const PasswordStrengthMeter = ({ password }: { password: string }) => {
  let score = 0;
  if (password.length > 8) score += 1;
  if (password.length > 12) score += 1;
  if (/[A-Z]/.test(password)) score += 1;
  if (/[0-9]/.test(password)) score += 1;
  if (/[^a-zA-Z0-9]/.test(password)) score += 1;

  let color = "bg-slate-700";
  let label = "Too short";
  if (score >= 1) { color = "bg-rose-500"; label = "Weak"; }
  if (score >= 3) { color = "bg-amber-500"; label = "Fair"; }
  if (score >= 4) { color = "bg-teal-500 shadow-[0_0_8px_rgba(20,184,166,0.6)]"; label = "Strong"; }

  return (
    <div className="mt-2">
      <div className="flex gap-1.5 h-1.5 w-full">
        {[1, 2, 3, 4, 5].map((level) => (
          <div 
            key={level} 
            className={`flex-1 rounded-full transition-all duration-500 ${score >= level ? color : "bg-slate-800"}`}
          />
        ))}
      </div>
      <div className="text-[10px] text-right text-slate-500 mt-1 font-semibold">{label}</div>
    </div>
  );
};

export default function RegisterPage() {
  const router = useRouter();
  const { toast } = useToast();

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [orgDisplayName, setOrgDisplayName] = useState("");
  const [orgSlug, setOrgSlug] = useState("");
  const [slugManuallyEdited, setSlugManuallyEdited] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  
  const [step, setStep] = useState(1); // 1 = Details, 2 = Workspace

  // Auto-generate slug from org display name
  useEffect(() => {
    if (!slugManuallyEdited && orgDisplayName) {
      setOrgSlug(slugify(orgDisplayName));
    }
  }, [orgDisplayName, slugManuallyEdited]);

  const passwordsMatch = confirmPassword === "" || password === confirmPassword;
  
  const handleNextStep = (e: React.MouseEvent) => {
    e.preventDefault();
    if (!username || !email || !password || !passwordsMatch || password.length < 8) {
      toast("Please fill in all required fields correctly", "warning");
      return;
    }
    setStep(2);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      toast("Passwords do not match", "error");
      return;
    }
    setIsLoading(true);

    try {
      await fetchAPI("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({
          org_slug: orgSlug,
          org_display_name: orgDisplayName,
          email,
          username,
          password,
          first_name: firstName || undefined,
          last_name: lastName || undefined,
        }),
      });

      toast("Workspace created! Please check your email to verify your account.", "success");
      router.push("/verify-email");
    } catch (err: any) {
      toast(err.message || "Failed to create workspace", "error");
    } finally {
      setIsLoading(false);
    }
  };

  const inputClass =
    "w-full bg-slate-900/50 border border-slate-700 rounded-xl pl-11 pr-4 py-3.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500/50 focus:border-teal-400 transition-all placeholder:text-slate-500 text-slate-200 font-medium backdrop-blur-sm shadow-inner group-hover:border-slate-600";
  const labelClass = "block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2 ml-1";

  return (
    <div className="min-h-screen w-full bg-slate-950 flex items-center justify-center p-4 relative overflow-hidden font-sans">
      {/* Deep animated background elements */}
      <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-20 mix-blend-overlay pointer-events-none z-0"></div>
      
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-teal-600/20 rounded-full blur-[120px] pointer-events-none animate-float z-0" style={{ animationDelay: '0s' }} />
      <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-indigo-600/20 rounded-full blur-[120px] pointer-events-none animate-float z-0" style={{ animationDelay: '-4s' }} />

      <div className="w-full max-w-xl auth-glass-dark rounded-3xl p-8 sm:p-10 relative z-10 my-8 animate-fade-slide-up">
        {/* Header */}
        <div className="flex flex-col items-center mb-8 relative">
          <div className="absolute inset-0 bg-teal-500/20 blur-2xl rounded-full scale-150"></div>
          <div className="h-14 w-14 rounded-2xl bg-gradient-to-tr from-teal-500 to-emerald-400 flex items-center justify-center text-white shadow-xl shadow-teal-900/50 border border-teal-400/30 mb-5 relative z-10">
            <Cpu className="h-7 w-7" />
          </div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight relative z-10">Create Workspace</h1>
          <p className="text-sm text-slate-400 mt-2 text-center font-medium relative z-10">
            Set up a new DevOps AI Hub organisation.
          </p>
        </div>

        {/* Step Indicator */}
        <div className="flex items-center justify-center mb-8 px-4">
          <div className={`flex flex-col items-center gap-2 ${step >= 1 ? 'text-teal-400' : 'text-slate-500'}`}>
            <div className={`h-8 w-8 rounded-full flex items-center justify-center border-2 font-bold text-xs ${step >= 1 ? 'border-teal-400 bg-teal-500/20 shadow-[0_0_10px_rgba(45,212,191,0.3)]' : 'border-slate-700 bg-slate-800'}`}>
              {step > 1 ? <Check className="h-4 w-4" /> : '1'}
            </div>
            <span className="text-[10px] uppercase tracking-widest font-bold">Details</span>
          </div>
          
          <div className="flex-1 h-px bg-slate-800 mx-4 relative">
            <div className={`absolute left-0 top-0 h-full bg-teal-400 transition-all duration-500 ${step === 2 ? 'w-full' : 'w-0'}`}></div>
          </div>
          
          <div className={`flex flex-col items-center gap-2 ${step >= 2 ? 'text-teal-400' : 'text-slate-500'}`}>
            <div className={`h-8 w-8 rounded-full flex items-center justify-center border-2 font-bold text-xs ${step >= 2 ? 'border-teal-400 bg-teal-500/20 shadow-[0_0_10px_rgba(45,212,191,0.3)] transition-all delay-300' : 'border-slate-700 bg-slate-800'}`}>
              2
            </div>
            <span className="text-[10px] uppercase tracking-widest font-bold">Workspace</span>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6 relative">
          {/* ── Step 1: Your Details ── */}
          <div className={`transition-all duration-500 absolute w-full ${step === 1 ? 'opacity-100 translate-x-0 relative' : 'opacity-0 -translate-x-full absolute pointer-events-none'}`}>
            
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div className="group">
                <label className={labelClass}>First Name</label>
                <div className="relative">
                  <User className="absolute left-4 top-1/2 -translate-y-1/2 h-4.5 w-4.5 text-slate-500 group-focus-within:text-teal-400 transition-colors" />
                  <input
                    id="first-name"
                    type="text"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    placeholder="John"
                    className={inputClass}
                  />
                </div>
              </div>
              <div className="group">
                <label className={labelClass}>Last Name</label>
                <div className="relative">
                  <User className="absolute left-4 top-1/2 -translate-y-1/2 h-4.5 w-4.5 text-slate-500 group-focus-within:text-teal-400 transition-colors" />
                  <input
                    id="last-name"
                    type="text"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    placeholder="Doe"
                    className={inputClass}
                  />
                </div>
              </div>
            </div>

            <div className="mb-4 group">
              <label className={labelClass}>
                Username <span className="text-teal-500 ml-1">*</span>
              </label>
              <div className="relative">
                <Hash className="absolute left-4 top-1/2 -translate-y-1/2 h-4.5 w-4.5 text-slate-500 group-focus-within:text-teal-400 transition-colors" />
                <input
                  id="username"
                  type="text"
                  required={step === 1}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="admin"
                  className={inputClass}
                />
              </div>
            </div>

            <div className="mb-4 group">
              <label className={labelClass}>
                Work Email <span className="text-teal-500 ml-1">*</span>
              </label>
              <div className="relative">
                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 h-4.5 w-4.5 text-slate-500 group-focus-within:text-teal-400 transition-colors" />
                <input
                  id="email"
                  type="email"
                  required={step === 1}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="admin@acme.com"
                  className={inputClass}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="group">
                <label className={labelClass}>
                  Password <span className="text-teal-500 ml-1">*</span>
                </label>
                <div className="relative">
                  <Lock className="absolute left-4 top-1/2 -translate-y-1/2 h-4.5 w-4.5 text-slate-500 group-focus-within:text-teal-400 transition-colors" />
                  <input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    required={step === 1}
                    minLength={8}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Min 8 chars"
                    className={inputClass.replace("pr-4", "pr-10")}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-500 hover:text-teal-400 transition-colors"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <PasswordStrengthMeter password={password} />
              </div>
              
              <div className="group">
                <label className={labelClass}>
                  Confirm <span className="text-teal-500 ml-1">*</span>
                </label>
                <div className="relative">
                  <Lock className="absolute left-4 top-1/2 -translate-y-1/2 h-4.5 w-4.5 text-slate-500 group-focus-within:text-teal-400 transition-colors" />
                  <input
                    id="confirm-password"
                    type={showConfirm ? "text" : "password"}
                    required={step === 1}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Repeat"
                    className={`${inputClass.replace("pr-4", "pr-10")} ${
                      !passwordsMatch ? "border-rose-500 focus:ring-rose-500/40 focus:border-rose-400" : ""
                    }`}
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirm(!showConfirm)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-500 hover:text-teal-400 transition-colors"
                  >
                    {showConfirm ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                {!passwordsMatch && (
                  <p className="text-[10px] text-rose-400 font-semibold mt-1.5 text-right">Passwords don't match</p>
                )}
              </div>
            </div>

            <button
              type="button"
              onClick={handleNextStep}
              className="w-full bg-slate-800 hover:bg-slate-700 border border-slate-700 text-white font-bold rounded-xl px-4 py-3.5 mt-8 shadow-md transition-all flex items-center justify-center gap-2 group"
            >
              Continue to Workspace Setup
              <ArrowRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
            </button>
          </div>

          {/* ── Step 2: Your Workspace ── */}
          <div className={`transition-all duration-500 absolute w-full top-0 ${step === 2 ? 'opacity-100 translate-x-0 relative' : 'opacity-0 translate-x-full absolute pointer-events-none'}`}>
            
            <div className="mb-6 group">
              <label className={labelClass}>
                Organisation Name <span className="text-teal-500 ml-1">*</span>
              </label>
              <div className="relative">
                <Building2 className="absolute left-4 top-1/2 -translate-y-1/2 h-4.5 w-4.5 text-slate-500 group-focus-within:text-teal-400 transition-colors" />
                <input
                  id="org-name"
                  type="text"
                  required={step === 2}
                  value={orgDisplayName}
                  onChange={(e) => setOrgDisplayName(e.target.value)}
                  placeholder="Acme Corporation"
                  className={inputClass}
                />
              </div>
            </div>

            <div className="mb-6 group">
              <label className={labelClass}>
                Organisation Slug <span className="text-teal-500 ml-1">*</span>
              </label>
              <div className="relative">
                <span className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500 text-sm font-bold select-none">/</span>
                <input
                  id="org-slug"
                  type="text"
                  required={step === 2}
                  pattern="^[a-z0-9][a-z0-9\-]*[a-z0-9]$"
                  title="Only lowercase letters, numbers, and hyphens. Cannot start or end with a hyphen."
                  value={orgSlug}
                  onChange={(e) => {
                    setSlugManuallyEdited(true);
                    setOrgSlug(e.target.value);
                  }}
                  placeholder="acme-corp"
                  className={inputClass.replace("pl-11", "pl-8")}
                />
              </div>
              <p className="text-[10px] text-slate-500 mt-2 ml-1 font-medium">
                Used for login URLs. Lowercase letters, numbers and hyphens only.
              </p>
            </div>

            <div className="flex gap-4 mt-8">
              <button
                type="button"
                onClick={() => setStep(1)}
                className="px-6 py-3.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-white font-bold rounded-xl transition-colors"
              >
                Back
              </button>
              
              <button
                type="submit"
                disabled={isLoading}
                className="flex-1 bg-gradient-to-r from-teal-500 to-emerald-500 hover:from-teal-400 hover:to-emerald-400 text-slate-950 font-bold rounded-xl px-4 py-3.5 shadow-[0_0_20px_rgba(20,184,166,0.3)] transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 group relative overflow-hidden"
              >
                <div className="absolute inset-0 bg-white/20 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-700 ease-in-out"></div>
                {isLoading ? (
                  <>
                    <Loader2 className="h-5 w-5 animate-spin" />
                    Creating...
                  </>
                ) : (
                  <>
                    Complete Registration
                    <Check className="h-4 w-4" />
                  </>
                )}
              </button>
            </div>
          </div>
        </form>

        <div className="mt-10 pt-6 border-t border-slate-800/60 text-center">
          <p className="text-sm text-slate-400 font-medium">
            Already have a workspace?{" "}
            <Link href="/login" className="font-bold text-teal-400 hover:text-teal-300 transition-colors drop-shadow-[0_0_8px_rgba(45,212,191,0.4)]">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
