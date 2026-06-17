"use client";

import React, { useState, useEffect } from "react";
import {
  User, Mail, Shield, Hash, Save,
  Lock, Eye, EyeOff, Loader2, CheckCircle
} from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { useToast } from "@/components/Toast";

interface Profile {
  id: string;
  username: string;
  email: string;
  display_name?: string;
  first_name?: string;
  last_name?: string;
  role: string;
  org_id: string;
  is_email_verified: boolean;
  login_count: number;
}

const roleBadge: Record<string, string> = {
  owner: "bg-amber-50 text-amber-700 border border-amber-200",
  admin: "bg-teal-50 text-teal-700 border border-teal-200",
  analyst: "bg-blue-50 text-blue-700 border border-blue-200",
  viewer: "bg-slate-100 text-slate-600 border border-slate-200",
};

function InitialsAvatar({ name }: { name: string }) {
  const initials = name
    .split(" ")
    .map((n) => n.charAt(0).toUpperCase())
    .slice(0, 2)
    .join("");
  return (
    <div className="h-16 w-16 rounded-2xl bg-gradient-to-tr from-teal-500 to-emerald-400 flex items-center justify-center text-white font-bold text-xl shadow-lg shadow-teal-500/20">
      {initials || "?"}
    </div>
  );
}

export default function ProfilePage() {
  const { toast } = useToast();

  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

  // Profile edit
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);

  // Password change
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);

  const passwordsMatch = confirmPassword === "" || newPassword === confirmPassword;

  useEffect(() => {
    fetchAPI("/api/users/me")
      .then((data: Profile) => {
        setProfile(data);
        setFirstName(data.first_name || "");
        setLastName(data.last_name || "");
        setDisplayName(data.display_name || "");
      })
      .catch((err: any) => toast(err.message || "Failed to load profile", "error"))
      .finally(() => setLoading(false));
  }, []);

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingProfile(true);
    try {
      const updated = await fetchAPI("/api/users/me", {
        method: "PATCH",
        body: JSON.stringify({
          first_name: firstName || null,
          last_name: lastName || null,
          display_name: displayName || null,
        }),
      });
      setProfile(updated);
      setFirstName(updated.first_name || "");
      setLastName(updated.last_name || "");
      setDisplayName(updated.display_name || "");
      toast("Profile updated successfully", "success");
    } catch (err: any) {
      toast(err.message || "Failed to update profile", "error");
    } finally {
      setSavingProfile(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      toast("Passwords do not match", "error");
      return;
    }
    setSavingPassword(true);
    try {
      await fetchAPI("/api/users/me/change-password", {
        method: "POST",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
          confirm_password: confirmPassword,
        }),
      });
      toast("Password changed successfully", "success");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: any) {
      toast(err.message || "Failed to change password", "error");
    } finally {
      setSavingPassword(false);
    }
  };

  const inputClass =
    "w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500/50 focus:border-teal-500 transition-all placeholder:text-slate-400 text-slate-800 font-medium";
  const labelClass = "block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5";

  if (loading) {
    return (
      <div className="space-y-6 max-w-2xl animate-pulse">
        <div className="h-6 w-40 bg-slate-200 rounded-lg" />
        <div className="h-40 bg-white border border-slate-200 rounded-2xl" />
        <div className="h-64 bg-white border border-slate-200 rounded-2xl" />
      </div>
    );
  }

  if (!profile) return null;

  const displayedName = profile.display_name || profile.username;

  return (
    <div className="max-w-2xl space-y-6 animate-fade-slide-up">
      {/* Profile Summary Card */}
      <div className="bg-white border border-slate-200 rounded-2xl shadow-xs p-6">
        <div className="flex items-center gap-5">
          <InitialsAvatar name={displayedName} />
          <div className="flex-1 min-w-0">
            <h2 className="text-xl font-bold text-slate-800 truncate">{displayedName}</h2>
            <p className="text-sm text-slate-500">@{profile.username}</p>
            <div className="flex flex-wrap items-center gap-2 mt-2">
              <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold ${roleBadge[profile.role] || roleBadge["viewer"]}`}>
                <Shield className="h-3 w-3" />
                {profile.role}
              </span>
              {profile.is_email_verified && (
                <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-emerald-50 border border-emerald-200 text-emerald-700">
                  <CheckCircle className="h-3 w-3" />
                  Email Verified
                </span>
              )}
            </div>
          </div>
          <div className="text-right hidden sm:block shrink-0">
            <div className="text-2xl font-bold text-slate-800">{profile.login_count}</div>
            <div className="text-xs text-slate-500 mt-0.5">Total Logins</div>
          </div>
        </div>

        {/* Read-only info row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-5 pt-5 border-t border-slate-100">
          <div className="flex items-center gap-3 bg-slate-50 rounded-xl p-3">
            <Mail className="h-4 w-4 text-slate-400 shrink-0" />
            <div className="min-w-0">
              <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Email</div>
              <div className="text-sm text-slate-700 font-medium truncate">{profile.email}</div>
            </div>
          </div>
          <div className="flex items-center gap-3 bg-slate-50 rounded-xl p-3">
            <Hash className="h-4 w-4 text-slate-400 shrink-0" />
            <div className="min-w-0">
              <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Username</div>
              <div className="text-sm text-slate-700 font-medium truncate">{profile.username}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Edit Profile Card */}
      <div className="bg-white border border-slate-200 rounded-2xl shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100">
          <h3 className="font-bold text-slate-800 flex items-center gap-2 text-sm">
            <User className="h-4 w-4 text-teal-600" />
            Edit Profile
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">Update your personal information.</p>
        </div>
        <form onSubmit={handleSaveProfile} className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={labelClass}>First Name</label>
              <input
                type="text"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                placeholder="John"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Last Name</label>
              <input
                type="text"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                placeholder="Doe"
                className={inputClass}
              />
            </div>
          </div>

          <div>
            <label className={labelClass}>Display Name</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="John Doe"
              className={inputClass}
            />
            <p className="text-[11px] text-slate-400 mt-1.5">
              This name is shown throughout the application. Auto-generated from First + Last Name if left blank.
            </p>
          </div>

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={savingProfile}
              className="flex items-center gap-2 bg-teal-600 hover:bg-teal-700 text-white text-sm font-semibold px-5 py-2.5 rounded-xl shadow-md shadow-teal-500/20 transition-all disabled:opacity-70 disabled:cursor-not-allowed"
            >
              {savingProfile ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {savingProfile ? "Saving..." : "Save Changes"}
            </button>
          </div>
        </form>
      </div>

      {/* Change Password Card */}
      <div className="bg-white border border-slate-200 rounded-2xl shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100">
          <h3 className="font-bold text-slate-800 flex items-center gap-2 text-sm">
            <Lock className="h-4 w-4 text-teal-600" />
            Change Password
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">Choose a strong password of at least 8 characters.</p>
        </div>
        <form onSubmit={handleChangePassword} className="p-6 space-y-4">
          <div>
            <label className={labelClass}>
              Current Password <span className="text-rose-500">*</span>
            </label>
            <div className="relative">
              <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <input
                type={showCurrent ? "text" : "password"}
                required
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                placeholder="Enter current password"
                className={`${inputClass} pl-10 pr-10`}
              />
              <button
                type="button"
                onClick={() => setShowCurrent(!showCurrent)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors"
              >
                {showCurrent ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={labelClass}>
                New Password <span className="text-rose-500">*</span>
              </label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <input
                  type={showNew ? "text" : "password"}
                  required
                  minLength={8}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Min 8 characters"
                  className={`${inputClass} pl-10 pr-10`}
                />
                <button
                  type="button"
                  onClick={() => setShowNew(!showNew)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors"
                >
                  {showNew ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            <div>
              <label className={labelClass}>
                Confirm Password <span className="text-rose-500">*</span>
              </label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <input
                  type={showConfirm ? "text" : "password"}
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Repeat new password"
                  className={`${inputClass} pl-10 pr-10 ${
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
                <p className="text-xs text-rose-500 mt-1.5">Passwords don't match</p>
              )}
            </div>
          </div>

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={savingPassword || !passwordsMatch}
              className="flex items-center gap-2 bg-teal-600 hover:bg-teal-700 text-white text-sm font-semibold px-5 py-2.5 rounded-xl shadow-md shadow-teal-500/20 transition-all disabled:opacity-70 disabled:cursor-not-allowed"
            >
              {savingPassword ? <Loader2 className="h-4 w-4 animate-spin" /> : <Lock className="h-4 w-4" />}
              {savingPassword ? "Changing..." : "Change Password"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
