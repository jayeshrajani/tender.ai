"use client";

import { AlertTriangle, Plus } from "lucide-react";
import { useState } from "react";

import { CertificateForm, CertificateTable } from "@/components/company/certificates";
import { Button } from "@/components/ui/button";
import { ErrorState, PageHeader, Panel, Skeleton } from "@/components/ui/display";
import { formatDateIST } from "@/lib/format";
import { canEdit, useProfile } from "@/lib/hooks";

export default function DocumentsPage() {
  const profile = useProfile();
  const [adding, setAdding] = useState(false);
  if (profile.isLoading) return <Skeleton className="h-96 w-full" />;
  if (profile.error || !profile.data) return <ErrorState message="Could not load documents." onRetry={() => void profile.refetch()} />;
  const p = profile.data;
  const canManage = canEdit(p.role, "admin");
  const attention = p.certificates.filter((c) => c.expiry_state === "expired" || c.expiry_state === "expiring");
  const unverified = p.certificates.filter((c) => c.verification_status !== "verified").length;

  return (
    <>
      <PageHeader
        title="Document vault"
        description="Your certificates power every eligibility check. Keep them verified and in date and more tenders turn green. Files stay private to your company."
        actions={
          canManage && !adding ? (
            <Button variant="primary" onClick={() => setAdding(true)}>
              <Plus /> Add certificate
            </Button>
          ) : null
        }
      />

      {attention.length ? (
        <div role="status" className="mb-4 rounded-lg border border-warn-line bg-warn-soft px-4 py-3 text-xs text-warn">
          <p className="flex items-center gap-1.5 font-semibold">
            <AlertTriangle className="size-3.5" aria-hidden /> Renewal needed
          </p>
          <ul className="mt-1 space-y-0.5">
            {attention.map((c) => (
              <li key={c.id}>
                {c.title} — {c.expiry_state === "expired" ? "expired" : "expires"} {formatDateIST(c.expires_on)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {adding ? (
        <Panel title="New certificate" className="mb-4">
          <CertificateForm onDone={() => setAdding(false)} />
        </Panel>
      ) : null}

      <Panel
        title="Certificates"
        description={`${p.certificates.length} on file · ${unverified} awaiting verification. “Mark verified” means a team admin checked the original with the issuing authority.`}
      >
        <CertificateTable certificates={p.certificates} canManage={canManage} />
      </Panel>
    </>
  );
}
