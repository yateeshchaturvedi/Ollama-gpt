"use client";

import React, { useState, useEffect, useCallback } from "react";
import Cookies from "js-cookie";
import {
  Users, UserPlus, Mail, Shield, Trash2, X, Loader2,
  Copy, Check, Clock, RefreshCw, ChevronDown
} from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { useToast } from "@/components/Toast";

function parseJwt(token: string) {
  try {
    return JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
  } catch {
    return null;
  }
}

const ROLES = ["viewer", "analyst", "admin"] as const;
type Role = typeof ROLES[number];

const roleBadge: Record<string, string> = {
  owner: "bg-amber-50 text-amber-700 border border-amber-200",
  admin: "bg-teal-50 text-teal-700 border border-teal-200",
  analyst: "bg-blue-50 text-blue-700 border border-blue-200",
  viewer: "bg-slate-100 text-slate-600 border border-slate-200",
};

interface Member {
  id: string; username: string; email: string; display_name?: string;
  role: string; is_active: boolean; is_invited: boolean; created_at: string;
}
interface Invite {
  id: string; invited_email: string; assigned_role: string;
  invite_code: string; expires_at: string; created_at: string;
}

export default function TeamMembersPage() {
  const { toast } = useToast();

  const [callerRole, setCallerRole] = useState<string>("");
  const [members, setMembers] = useState<Member[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(true);
  const [loadingInvites, setLoadingInvites] = useState(true);

  // Invite modal
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<Role>("viewer");
  const [inviting, setInviting] = useState(false);

  // Action states
  const [changingRole, setChangingRole] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  useEffect(() => {
    const token = Cookies.get("access_token");
    if (token) {
      const p = parseJwt(token);
      if (p) setCallerRole(p.role);
    }
  }, []);

  const loadMembers = useCallback(async () => {
    setLoadingMembers(true);
    try {
      const data = await fetchAPI("/api/admin/users");
      setMembers(data);
    } catch (err: any) {
      toast(err.message || "Failed to load members", "error");
    } finally {
      setLoadingMembers(false);
    }
  }, []);

  const loadInvites = useCallback(async () => {
    setLoadingInvites(true);
    try {
      const data = await fetchAPI("/api/admin/users/invites");
      setInvites(data);
    } catch (err: any) {
      toast(err.message || "Failed to load invites", "error");
    } finally {
      setLoadingInvites(false);
    }
  }, []);

  useEffect(() => {
    loadMembers();
    loadInvites();
  }, [loadMembers, loadInvites]);

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    setInviting(true);
    try {
      await fetchAPI("/api/admin/users/invites", {
        method: "POST",
        body: JSON.stringify({ email: inviteEmail, role: inviteRole }),
      });
      toast(`Invite sent to ${inviteEmail}`, "success");
      setShowInviteModal(false);
      setInviteEmail("");
      setInviteRole("viewer");
      loadInvites();
    } catch (err: any) {
      toast(err.message || "Failed to send invite", "error");
    } finally {
      setInviting(false);
    }
  };

  const handleDeleteMember = async (userId: string, username: string) => {
    if (!confirm(`Remove ${username} from the organisation? This action cannot be undone.`)) return;
    setDeletingId(userId);
    try {
      await fetchAPI(`/api/admin/users/${userId}`, { method: "DELETE" });
      toast(`${username} has been removed`, "success");
      loadMembers();
    } catch (err: any) {
      toast(err.message || "Failed to remove member", "error");
    } finally {
      setDeletingId(null);
    }
  };

  const handleChangeRole = async (userId: string, newRole: string) => {
    setChangingRole(userId);
    try {
      await fetchAPI(`/api/admin/users/${userId}/role`, {
        method: "PATCH",
        body: JSON.stringify({ role: newRole }),
      });
      toast("Role updated", "success");
      loadMembers();
    } catch (err: any) {
      toast(err.message || "Failed to update role", "error");
    } finally {
      setChangingRole(null);
    }
  };

  const handleRevokeInvite = async (inviteId: string, email: string) => {
    if (!confirm(`Revoke the invite for ${email}?`)) return;
    setRevokingId(inviteId);
    try {
      await fetchAPI(`/api/admin/users/invites/${inviteId}`, { method: "DELETE" });
      toast("Invite revoked", "success");
      loadInvites();
    } catch (err: any) {
      toast(err.message || "Failed to revoke invite", "error");
    } finally {
      setRevokingId(null);
    }
  };

  const copyInviteLink = (code: string) => {
    const link = `${window.location.origin}/accept-invite?code=${code}`;
    navigator.clipboard.writeText(link);
    setCopiedCode(code);
    toast("Invite link copied to clipboard", "success");
    setTimeout(() => setCopiedCode(null), 2000);
  };

  const inputClass =
    "w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500/50 focus:border-teal-500 transition-all placeholder:text-slate-400 text-slate-800 font-medium";

  return (
    <div className="max-w-4xl space-y-6 animate-fade-slide-up">
      {/* Header */}
      <div className="flex items-center justify-between bg-white border border-slate-200 p-6 rounded-2xl">
        <div>
          <h2 className="text-xl font-bold text-slate-800 tracking-tight flex items-center gap-2">
            <Users className="h-5 w-5 text-teal-600" />
            Team Members
          </h2>
          <p className="text-slate-500 text-xs mt-1 leading-relaxed">
            Manage your organisation's members and invitations.
          </p>
        </div>
        <button
          onClick={() => setShowInviteModal(true)}
          className="flex items-center gap-2 bg-teal-600 hover:bg-teal-700 text-white text-sm font-semibold px-4 py-2.5 rounded-xl shadow-md shadow-teal-500/20 transition-all"
        >
          <UserPlus className="h-4 w-4" />
          Invite User
        </button>
      </div>

      {/* Members Table */}
      <div className="bg-white border border-slate-200 rounded-2xl shadow-xs overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h3 className="font-bold text-slate-800 text-sm flex items-center gap-2">
            <Users className="h-4 w-4 text-slate-400" />
            Members ({members.length})
          </h3>
          <button
            onClick={loadMembers}
            className="p-1.5 text-slate-400 hover:text-teal-600 hover:bg-teal-50 rounded-lg transition-all"
            title="Refresh"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>

        {loadingMembers ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-6 w-6 text-teal-600 animate-spin" />
          </div>
        ) : members.length === 0 ? (
          <div className="text-center py-16 text-slate-400 text-sm">No members found.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/60">
                  <th className="text-left text-[10px] font-bold text-slate-500 uppercase tracking-wider px-6 py-3">User</th>
                  <th className="text-left text-[10px] font-bold text-slate-500 uppercase tracking-wider px-6 py-3">Email</th>
                  <th className="text-left text-[10px] font-bold text-slate-500 uppercase tracking-wider px-6 py-3">Role</th>
                  <th className="text-left text-[10px] font-bold text-slate-500 uppercase tracking-wider px-6 py-3">Joined</th>
                  <th className="text-right text-[10px] font-bold text-slate-500 uppercase tracking-wider px-6 py-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {members.map((m) => (
                  <tr key={m.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="h-8 w-8 rounded-full bg-gradient-to-tr from-teal-500 to-emerald-400 flex items-center justify-center text-white font-bold text-xs shrink-0 shadow-sm">
                          {(m.display_name || m.username).charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <div className="font-semibold text-slate-800">{m.display_name || m.username}</div>
                          <div className="text-xs text-slate-400">@{m.username}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-slate-600">{m.email}</td>
                    <td className="px-6 py-4">
                      {m.role === "owner" ? (
                        <span className={`inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-semibold ${roleBadge["owner"]}`}>
                          owner
                        </span>
                      ) : (
                        <div className="relative inline-flex items-center">
                          <select
                            value={m.role}
                            disabled={changingRole === m.id}
                            onChange={(e) => handleChangeRole(m.id, e.target.value)}
                            className={`appearance-none pl-2.5 pr-7 py-1 rounded-lg text-xs font-semibold border cursor-pointer transition-all ${roleBadge[m.role] || roleBadge["viewer"]} bg-transparent`}
                          >
                            {ROLES.filter((r) => r !== "admin" || callerRole === "owner").map((r) => (
                              <option key={r} value={r} className="bg-white text-slate-800">{r}</option>
                            ))}
                          </select>
                          {changingRole === m.id
                            ? <Loader2 className="absolute right-1.5 top-1/2 -translate-y-1/2 h-3 w-3 animate-spin text-slate-500" />
                            : <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 h-3 w-3 text-slate-400 pointer-events-none" />
                          }
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4 text-slate-400 text-xs">
                      {new Date(m.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 text-right">
                      {m.role !== "owner" && (
                        <button
                          onClick={() => handleDeleteMember(m.id, m.username)}
                          disabled={deletingId === m.id}
                          className="p-1.5 text-slate-400 hover:text-rose-500 hover:bg-rose-50 rounded-lg transition-all"
                          title="Remove member"
                        >
                          {deletingId === m.id
                            ? <Loader2 className="h-4 w-4 animate-spin" />
                            : <Trash2 className="h-4 w-4" />
                          }
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pending Invites */}
      <div className="bg-white border border-slate-200 rounded-2xl shadow-xs overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h3 className="font-bold text-slate-800 text-sm flex items-center gap-2">
            <Mail className="h-4 w-4 text-slate-400" />
            Pending Invites ({invites.length})
          </h3>
          <button
            onClick={loadInvites}
            className="p-1.5 text-slate-400 hover:text-teal-600 hover:bg-teal-50 rounded-lg transition-all"
            title="Refresh"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>

        {loadingInvites ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 text-teal-600 animate-spin" />
          </div>
        ) : invites.length === 0 ? (
          <div className="text-center py-12 text-slate-400 text-sm">No pending invitations.</div>
        ) : (
          <div className="divide-y divide-slate-100">
            {invites.map((inv) => (
              <div key={inv.id} className="flex items-center justify-between px-6 py-4 hover:bg-slate-50/70 transition-colors">
                <div className="flex items-center gap-3">
                  <div className="h-8 w-8 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center shrink-0">
                    <Mail className="h-4 w-4 text-slate-400" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-slate-800">{inv.invited_email}</div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold ${roleBadge[inv.assigned_role] || roleBadge["viewer"]}`}>
                        {inv.assigned_role}
                      </span>
                      <span className="text-[11px] text-slate-400 flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        Expires {new Date(inv.expires_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => copyInviteLink(inv.invite_code)}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-600 hover:text-teal-700 hover:bg-teal-50 border border-slate-200 hover:border-teal-200 rounded-lg transition-all"
                    title="Copy invite link"
                  >
                    {copiedCode === inv.invite_code ? <Check className="h-3.5 w-3.5 text-teal-600" /> : <Copy className="h-3.5 w-3.5" />}
                    {copiedCode === inv.invite_code ? "Copied!" : "Copy Link"}
                  </button>
                  <button
                    onClick={() => handleRevokeInvite(inv.id, inv.invited_email)}
                    disabled={revokingId === inv.id}
                    className="p-1.5 text-slate-400 hover:text-rose-500 hover:bg-rose-50 rounded-lg transition-all"
                    title="Revoke invite"
                  >
                    {revokingId === inv.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <X className="h-4 w-4" />}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Invite Modal */}
      {showInviteModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-white border border-slate-200 rounded-2xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                <UserPlus className="h-5 w-5 text-teal-600" />
                Invite Team Member
              </h3>
              <button
                onClick={() => setShowInviteModal(false)}
                className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleInvite} className="space-y-4">
              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">
                  Email Address <span className="text-rose-500">*</span>
                </label>
                <div className="relative">
                  <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                  <input
                    type="email"
                    required
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    placeholder="colleague@company.com"
                    className={`${inputClass} pl-10`}
                  />
                </div>
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">
                  Role
                </label>
                <div className="relative">
                  <Shield className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                  <select
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value as Role)}
                    className={`${inputClass} pl-10 appearance-none`}
                  >
                    <option value="viewer">Viewer — Read-only access</option>
                    <option value="analyst">Analyst — Can run analyses</option>
                    {callerRole === "owner" && (
                      <option value="admin">Admin — Full admin access</option>
                    )}
                  </select>
                </div>
              </div>

              <div className="bg-teal-50 border border-teal-200 rounded-xl p-3 text-xs text-teal-700">
                An invitation email will be sent automatically. The link expires in <strong>7 days</strong>.
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowInviteModal(false)}
                  className="flex-1 py-2.5 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 text-sm font-medium transition-all"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={inviting}
                  className="flex-1 py-2.5 rounded-xl bg-teal-600 hover:bg-teal-700 text-white text-sm font-semibold transition-all disabled:opacity-70 flex items-center justify-center gap-2"
                >
                  {inviting ? <><Loader2 className="h-4 w-4 animate-spin" />Sending...</> : "Send Invite"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
