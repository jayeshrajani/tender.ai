"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import type { Me } from "@/lib/types";

interface Preview {
  company: string;
  email: string;
  role: string;
  account_exists: boolean;
}

export default function InvitePage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const preview = useQuery({ queryKey: ["invite", token], queryFn: () => api<Preview>(`/api/v1/auth/invitations/${token}`) });

  if (preview.isLoading) return <p className="text-sm text-muted">Checking invitation…</p>;
  if (preview.error || !preview.data)
    return <p role="alert" className="text-sm text-danger">This invitation is invalid or has expired. Ask your admin for a new link.</p>;

  const p = preview.data;
  async function accept(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await api<Me>("/api/v1/auth/accept-invite", {
        method: "POST",
        json: { token, password, full_name: p.account_exists ? undefined : name },
      });
      qc.setQueryData(["me"], me);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not accept the invitation.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1 className="text-xl font-semibold">Join {p.company}</h1>
      <p className="mt-1 text-sm text-muted">
        Invitation for <span className="font-medium text-ink">{p.email}</span> as <span className="capitalize">{p.role}</span>.
      </p>
      <form onSubmit={accept} className="mt-6 space-y-4">
        {!p.account_exists ? (
          <Field label="Your name" htmlFor="name" required>
            <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required minLength={2} />
          </Field>
        ) : null}
        <Field
          label={p.account_exists ? "Password for your existing account" : "Choose a password"}
          htmlFor="password"
          hint={p.account_exists ? undefined : "At least 10 characters."}
          required
        >
          <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={p.account_exists ? 1 : 10} />
        </Field>
        {error ? (
          <p role="alert" className="text-xs text-danger">
            {error}
          </p>
        ) : null}
        <Button type="submit" variant="primary" size="lg" className="w-full" disabled={busy}>
          {busy ? "Joining…" : "Accept invitation"}
        </Button>
      </form>
    </>
  );
}
