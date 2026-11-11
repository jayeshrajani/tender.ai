"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, UserPlus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Chip, ErrorState, PageHeader, Panel, Skeleton } from "@/components/ui/display";
import { Field, Input, Select } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { formatDateIST, formatDateTimeIST } from "@/lib/format";
import { canEdit } from "@/lib/hooks";
import type { Role } from "@/lib/types";

interface Team {
  members: { id: string; full_name: string; email: string; role: Role; joined_at: string; last_login_at: string | null; is_you: boolean }[];
  invitations: { id: string; email: string; role: Role; expires_at: string }[];
  roles: Record<Role, string>;
  your_role: Role;
}

interface AuditItem {
  id: string;
  action: string;
  actor: string;
  entity_type: string | null;
  data: Record<string, unknown>;
  created_at: string;
}

function Audit() {
  const q = useQuery({ queryKey: ["audit"], queryFn: () => api<{ items: AuditItem[] }>("/api/v1/team/audit") });
  if (q.isLoading) return <Skeleton className="h-40 w-full" />;
  if (q.error) return <p className="text-xs text-muted">{q.error.message}</p>;
  return (
    <ul className="divide-y divide-line text-xs">
      {q.data?.items.map((e) => (
        <li key={e.id} className="grid gap-1 py-2 md:grid-cols-[170px_160px_minmax(0,1fr)]">
          <span className="tabular text-muted">{formatDateTimeIST(e.created_at)}</span>
          <span className="font-medium">{e.actor}</span>
          <span>
            <span className="font-mono text-2xs">{e.action}</span>{" "}
            <span className="text-muted">{Object.entries(e.data).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`).join(" · ").slice(0, 200)}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function TeamPage() {
  const qc = useQueryClient();
  const team = useQuery({ queryKey: ["team"], queryFn: () => api<Team>("/api/v1/team") });
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("analyst");
  const [link, setLink] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const invite = useMutation({
    mutationFn: () => api<{ invite_path: string }>("/api/v1/team/invitations", { method: "POST", json: { email, role } }),
    onSuccess: (r) => {
      setLink(`${window.location.origin}${r.invite_path}`);
      setEmail("");
      void qc.invalidateQueries({ queryKey: ["team"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not invite"),
  });
  const changeRole = useMutation({
    mutationFn: ({ id, role }: { id: string; role: Role }) => api(`/api/v1/team/members/${id}`, { method: "PATCH", json: { role } }),
    onSuccess: () => {
      toast.success("Role updated");
      void qc.invalidateQueries({ queryKey: ["team"] });
      void qc.invalidateQueries({ queryKey: ["audit"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const removeMember = useMutation({
    mutationFn: (id: string) => api(`/api/v1/team/members/${id}`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["team"] }),
    onError: (e: Error) => toast.error(e.message),
  });
  const revoke = useMutation({
    mutationFn: (id: string) => api(`/api/v1/team/invitations/${id}`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["team"] }),
  });

  if (team.isLoading) return <Skeleton className="h-96 w-full" />;
  if (team.error || !team.data) return <ErrorState message="Could not load team." onRetry={() => void team.refetch()} />;
  const t = team.data;
  const isAdmin = canEdit(t.your_role, "admin");
  const isOwner = t.your_role === "owner";

  return (
    <>
      <PageHeader title="Team" description="Bring in your estimator, accountant or partner. Everyone gets the right access, and every change is logged." />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Panel title="Members" description={`${t.members.length} people with access to this company.`} bodyClassName="px-0 pb-0">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Company members</caption>
            <thead className="border-y border-line bg-subtle/50 text-2xs uppercase tracking-[0.05em] text-muted">
              <tr>
                <th scope="col" className="px-5 py-2.5 font-medium">Member</th>
                <th scope="col" className="px-3 py-2.5 font-medium">Role</th>
                <th scope="col" className="hidden px-3 py-2.5 font-medium md:table-cell">Last sign-in</th>
                <th scope="col" className="w-20 px-5 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {t.members.map((m) => (
                <tr key={m.id} className="border-b border-line last:border-0">
                  <td className="px-5 py-3">
                    <p className="font-medium">
                      {m.full_name} {m.is_you ? <span className="text-2xs font-normal text-muted">(you)</span> : null}
                    </p>
                    <p className="text-2xs text-muted">{m.email}</p>
                  </td>
                  <td className="px-3 py-3">
                    {isOwner && !m.is_you ? (
                      <Select aria-label={`Role for ${m.full_name}`} value={m.role} onChange={(e) => changeRole.mutate({ id: m.id, role: e.target.value as Role })} className="h-8 w-32 capitalize">
                        {(["owner", "admin", "analyst", "viewer"] as Role[]).map((r) => (
                          <option key={r} value={r}>
                            {r}
                          </option>
                        ))}
                      </Select>
                    ) : (
                      <Chip tone={m.role === "owner" ? "accent" : "outline"} className="capitalize">
                        {m.role}
                      </Chip>
                    )}
                  </td>
                  <td className="hidden px-3 py-3 text-xs text-muted md:table-cell">{m.last_login_at ? formatDateTimeIST(m.last_login_at) : "Never"}</td>
                  <td className="px-5 py-3 text-right">
                    {isAdmin && !m.is_you ? (
                      <Button size="sm" variant="quiet" onClick={() => removeMember.mutate(m.id)}>
                        Remove
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <div className="space-y-6">
          {isAdmin ? (
            <Panel title="Invite a colleague" description="No email is sent in V1. Share the one-time link directly; it expires in 7 days.">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  setError(null);
                  setLink(null);
                  invite.mutate();
                }}
                className="space-y-3"
              >
                <Field label="Email" htmlFor="invite-email" error={error ?? undefined}>
                  <Input id="invite-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
                </Field>
                <Field label="Role" htmlFor="invite-role">
                  <Select id="invite-role" value={role} onChange={(e) => setRole(e.target.value as Role)}>
                    <option value="admin">Admin</option>
                    <option value="analyst">Analyst</option>
                    <option value="viewer">Viewer</option>
                  </Select>
                </Field>
                <Button type="submit" variant="primary" disabled={!email || invite.isPending}>
                  <UserPlus /> Create invitation
                </Button>
              </form>
              {link ? (
                <div className="mt-3 rounded-md border border-line bg-subtle/50 p-2 text-2xs">
                  <p className="break-all font-mono">{link}</p>
                  <Button size="sm" variant="link" onClick={() => void navigator.clipboard.writeText(link).then(() => toast.success("Copied"))}>
                    <Copy /> Copy link
                  </Button>
                </div>
              ) : null}
              {t.invitations.length ? (
                <ul className="mt-4 space-y-1.5 border-t border-line pt-3 text-xs">
                  {t.invitations.map((i) => (
                    <li key={i.id} className="flex items-center justify-between gap-2">
                      <span className="min-w-0 truncate">
                        {i.email} <span className="capitalize text-muted">· {i.role} · until {formatDateIST(i.expires_at)}</span>
                      </span>
                      <Button size="sm" variant="quiet" onClick={() => revoke.mutate(i.id)}>
                        Revoke
                      </Button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </Panel>
          ) : null}
          <Panel title="Role permissions">
            <dl className="divide-y divide-line text-xs">
              {(Object.entries(t.roles) as [Role, string][]).map(([r, d]) => (
                <div key={r} className="grid grid-cols-[72px_minmax(0,1fr)] gap-3 py-2 first:pt-0 last:pb-0">
                  <dt className="font-medium capitalize">{r}</dt>
                  <dd className="text-muted">{d}</dd>
                </div>
              ))}
            </dl>
          </Panel>
        </div>
      </div>

      {isAdmin ? (
        <Panel title="Audit history" className="mt-6">
          <Audit />
        </Panel>
      ) : null}
    </>
  );
}
