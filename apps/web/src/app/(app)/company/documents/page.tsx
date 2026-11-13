"use client";

import { CheckCircle2, Plus } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import AppleActivityCard, { type ActivityData } from "@/components/kokonutui/apple-activity-card";
import { CertificateForm, CertificateWallet } from "@/components/company/certificates";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Panel, Skeleton } from "@/components/ui/display";
import { cn } from "@/lib/cn";
import { formatDateIST } from "@/lib/format";
import { canEdit, useProfile } from "@/lib/hooks";
import type { Certificate } from "@/lib/types";

type Filter = "all" | "attention" | "verified";

const needsAttention = (c: Certificate) =>
  c.expiry_state === "expired" || c.expiry_state === "expiring" || c.verification_status !== "verified" || !c.document;

function Segmented({ value, onChange, counts }: { value: Filter; onChange: (f: Filter) => void; counts: Record<Filter, number> }) {
  const options: [Filter, string][] = [
    ["all", "All"],
    ["attention", "Needs attention"],
    ["verified", "Verified"],
  ];
  return (
    <div role="group" aria-label="Filter certificates" className="inline-flex rounded-full bg-subtle p-1">
      {options.map(([key, label]) => (
        <button
          key={key}
          type="button"
          aria-pressed={value === key}
          onClick={() => onChange(key)}
          className={cn(
            "h-7 rounded-full px-3.5 text-[13px] font-medium transition-[background-color,color,box-shadow] duration-200 ease-snappy",
            value === key ? "bg-surface text-ink shadow-card" : "text-muted hover:text-ink",
          )}
        >
          {label} <span className="tabular text-faint">{counts[key]}</span>
        </button>
      ))}
    </div>
  );
}

function Renewals({ certificates }: { certificates: Certificate[] }) {
  const due = certificates
    .filter((c) => c.expiry_state === "expired" || c.expiry_state === "expiring")
    .sort((a, b) => (a.expires_on ?? "").localeCompare(b.expires_on ?? ""));
  return (
    <section aria-labelledby="renewals-title" className="flex flex-col rounded-[28px] bg-surface p-8">
      <h2 id="renewals-title" className="text-2xl font-medium">
        Renewals
      </h2>
      <p className="mt-1 text-[13px] text-muted">Expired certificates never count as evidence.</p>
      {due.length ? (
        <ul className="mt-5 divide-y divide-line">
          {due.map((c) => (
            <li key={c.id} className="flex items-baseline justify-between gap-4 py-3 first:pt-0">
              <span className="min-w-0 truncate text-[15px] font-medium">{c.title}</span>
              <span className={cn("tabular shrink-0 text-[13px] font-medium", c.expiry_state === "expired" ? "text-danger" : "text-warn")}>
                {c.expiry_state === "expired" ? "Expired" : "Expires"} {formatDateIST(c.expires_on)}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 py-8 text-center">
          <CheckCircle2 className="size-8 text-ok" strokeWidth={1.5} aria-hidden />
          <p className="text-[15px] font-medium">Nothing to renew</p>
          <p className="text-[13px] text-muted">Every certificate with an expiry date is in date.</p>
        </div>
      )}
    </section>
  );
}

export default function DocumentsPage() {
  const profile = useProfile();
  const [editing, setEditing] = useState<"new" | Certificate | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const formRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (editing) formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [editing]);

  if (profile.isLoading) return <Skeleton className="h-96 w-full rounded-[28px]" />;
  if (profile.error || !profile.data) return <ErrorState message="Could not load documents." onRetry={() => void profile.refetch()} />;
  const p = profile.data;
  const certs = p.certificates;
  const canManage = canEdit(p.role, "admin");
  const total = certs.length;
  const counts: Record<Filter, number> = {
    all: total,
    attention: certs.filter(needsAttention).length,
    verified: certs.filter((c) => c.verification_status === "verified").length,
  };
  const shown = filter === "all" ? certs : filter === "attention" ? certs.filter(needsAttention) : certs.filter((c) => c.verification_status === "verified");
  const target = Math.max(total, 1);
  const rings: ActivityData[] = [
    { label: "VERIFIED", color: "#FA114F", colorEnd: "#FF6B8B", size: 200, current: counts.verified, target, unit: "CERTS" },
    { label: "IN DATE", color: "#A3F900", colorEnd: "#C5FF4D", size: 160, current: certs.filter((c) => c.expiry_state !== "expired").length, target, unit: "CERTS" },
    { label: "FILE ON RECORD", color: "#04C7DD", colorEnd: "#4DDFED", size: 120, current: certs.filter((c) => c.document).length, target, unit: "CERTS" },
  ];

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-6">
        <div className="min-w-0">
          <h1 className="text-[2.5rem] font-semibold leading-[1.05] tracking-[-0.03em] md:text-[3.25rem]">Document vault</h1>
          <p className="mt-3 max-w-xl text-[17px] leading-relaxed text-muted">
            Your certificates power every eligibility check. Keep them verified and in date, and more tenders turn green.
          </p>
        </div>
        {canManage ? (
          <Button variant="primary" size="lg" onClick={() => setEditing("new")}>
            <Plus /> Add certificate
          </Button>
        ) : null}
      </header>

      <div className="mb-10 grid gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <AppleActivityCard title="Readiness" activities={rings} className="mx-0 max-w-none rounded-[28px] bg-surface" />
        <Renewals certificates={certs} />
      </div>

      {editing ? (
        <div ref={formRef} className="scroll-mt-24">
          <Panel
            title={editing === "new" ? "New certificate" : `Replace file · ${editing.title}`}
            description="PDF, JPG or PNG up to 20 MB. Files stay private to your company."
            className="mb-8"
          >
            <CertificateForm key={editing === "new" ? "new" : editing.id} existing={editing === "new" ? undefined : editing} onDone={() => setEditing(null)} />
          </Panel>
        </div>
      ) : null}

      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <h2 className="text-[22px] font-semibold tracking-[-0.022em]">Certificates</h2>
        {total ? <Segmented value={filter} onChange={setFilter} counts={counts} /> : null}
      </div>

      {total === 0 && !canManage ? (
        <div className="rounded-[22px] bg-surface">
          <EmptyState title="No certificates yet" body="An admin can add GST, registration and turnover certificates here." />
        </div>
      ) : total > 0 && shown.length === 0 ? (
        <div className="rounded-[22px] bg-surface">
          <EmptyState icon={CheckCircle2} title="All clear" body="No certificates match this filter." />
        </div>
      ) : (
        <CertificateWallet certificates={shown} canManage={canManage} onAdd={filter === "all" ? () => setEditing("new") : undefined} onReplace={setEditing} />
      )}

      <p className="mt-6 text-xs text-faint">“Mark verified” means a team admin checked the original with the issuing authority. TenderOS does not verify automatically.</p>
    </div>
  );
}
