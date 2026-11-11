"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Lock, Play, ShieldAlert } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { toast } from "sonner";

import { ImportPanel } from "@/components/sources/import-panel";
import { Button } from "@/components/ui/button";
import { Chip, ErrorState, PageHeader, Panel, Skeleton } from "@/components/ui/display";
import { api } from "@/lib/api";
import { formatDateTimeIST, titleCase } from "@/lib/format";
import { canEdit, useMe } from "@/lib/hooks";
import type { SourceItem, SourceRun, SourcesResponse } from "@/lib/types";

const STATE_TONE = (s: SourceItem) =>
  s.collection_state.startsWith("Disabled") ? "danger" : s.collection_state === "Demo data" ? "outline" : s.collection_state === "Manual import" ? "accent" : "muted";

const GROUPS: { title: string; description: string; test: (s: SourceItem) => boolean }[] = [
  {
    title: "Collection in TenderOS",
    description: "How tenders actually enter the system today.",
    test: (s) => ["demo", "manual_import", "official_feed"].includes(s.kind) || s.code === "mp_public_homepage",
  },
  {
    title: "Official tender portals",
    description: "Web pages, not APIs. Accessed by a person; imported manually.",
    test: (s) => ["government_portal", "department_site", "legal_terms"].includes(s.kind) && s.code !== "mp_public_homepage",
  },
  {
    title: "Qualification & reference sources",
    description: "Used by people to verify certificates and rates. Not collected.",
    test: (s) => ["qualification_reference", "company_reference", "rate_reference"].includes(s.kind),
  },
  { title: "Messaging", description: "Official Meta WhatsApp Cloud API.", test: (s) => s.kind === "messaging_api" },
];

function SourceTable({ items }: { items: SourceItem[] }) {
  return (
    <ul aria-label="Collection sources" className="divide-y divide-line">
      {items.map((s) => (
        <li key={s.id} className="grid gap-x-6 gap-y-2 py-4 first:pt-0 last:pb-0 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto]">
          <div className="min-w-0">
            <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
              {s.name}
              <Chip tone={STATE_TONE(s)}>{s.collection_state}</Chip>
            </p>
            <p className="mt-0.5 text-2xs text-muted">
              {s.owner_organization} · {titleCase(s.permission_status)}
            </p>
            {s.url && !s.url.includes("{") ? (
              <a href={s.url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-flex items-center gap-0.5 text-2xs text-accent hover:underline">
                Official link <ExternalLink className="size-3" aria-hidden />
              </a>
            ) : null}
          </div>
          <div className="min-w-0 text-xs text-muted">
            <p>{s.coverage_note}</p>
            {s.captcha_dependency ? (
              <p className="mt-1 inline-flex items-center gap-1 text-2xs">
                <Lock className="size-3" aria-hidden /> CAPTCHA – manual access only
              </p>
            ) : null}
            {s.last_failure_at ? (
              <p className="mt-1 text-2xs text-danger">
                Failed {formatDateTimeIST(s.last_failure_at)}: {s.last_error}
              </p>
            ) : null}
          </div>
          <div className="flex gap-6 text-xs md:justify-end md:text-right">
            <div>
              <p className="section-label">Tenders</p>
              <p className="tabular mt-0.5 text-sm font-medium">{s.tender_count || "—"}</p>
            </div>
            <div>
              <p className="section-label">Last success</p>
              <p className="tabular mt-0.5 whitespace-nowrap">{s.last_success_at ? formatDateTimeIST(s.last_success_at) : <span className="text-muted">Never</span>}</p>
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

function ReferenceList({ title, items }: { title: string; items: SourceItem[] }) {
  if (!items.length) return null;
  return (
    <div className="py-1">
      <h3 className="section-label mb-1 mt-2">{title}</h3>
      <ul className="divide-y divide-line">
        {items.map((s) => (
          <li key={s.id} className="flex items-center gap-3 py-2.5">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm">{s.name}</p>
              <p className="truncate text-2xs text-muted" title={s.coverage_note}>
                {s.owner_organization} · {s.api_status}
              </p>
            </div>
            {s.captcha_dependency ? <Lock className="size-3.5 shrink-0 text-faint" aria-label="CAPTCHA – manual access only" /> : null}
            {s.url && !s.url.includes("{") ? (
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex shrink-0 items-center gap-0.5 rounded-md px-1.5 py-1 text-2xs text-accent hover:bg-accent-soft"
                aria-label={`Open ${s.name}`}
              >
                Open <ExternalLink className="size-3" aria-hidden />
              </a>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Runs() {
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api<{ items: SourceRun[] }>("/api/v1/ingestion/runs") });
  if (runs.isLoading) return <Skeleton className="h-40 w-full" />;
  if (!runs.data?.items.length) return <p className="text-xs text-muted">No ingestion runs yet.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-left text-xs">
        <caption className="sr-only">Recent ingestion jobs</caption>
        <thead className="border-b border-line text-2xs uppercase tracking-[0.05em] text-muted">
          <tr>
            <th scope="col" className="py-2.5 pr-3 font-medium">Started</th>
            <th scope="col" className="px-3 py-2.5 font-medium">Source</th>
            <th scope="col" className="px-3 py-2.5 font-medium">Status</th>
            <th scope="col" className="px-3 py-2.5 font-medium">Records</th>
            <th scope="col" className="py-2.5 pl-3 font-medium">Detail</th>
          </tr>
        </thead>
        <tbody>
          {runs.data.items.map((r) => (
            <tr key={r.id} className="border-b border-line align-top last:border-0">
              <td className="py-2.5 pr-3">
                <p className="tabular whitespace-nowrap">{formatDateTimeIST(r.started_at)}</p>
                <p className="text-2xs capitalize text-muted" title={r.slot_key ?? undefined}>
                  {r.trigger}
                </p>
              </td>
              <td className="px-3 py-2.5">{r.source_name}</td>
              <td className="px-3 py-2.5">
                <Chip tone={r.status === "succeeded" ? "ok" : r.status === "skipped" ? "muted" : r.status === "partial" ? "warn" : "danger"} className="capitalize">
                  {r.status}
                </Chip>
                {r.attempt > 1 ? <span className="ml-1 text-2xs text-muted">attempt {r.attempt}</span> : null}
              </td>
              <td className="tabular whitespace-nowrap px-3 py-2.5 text-muted" title="created / updated / unchanged / duplicates / failed">
                {r.records_created + r.records_updated + r.records_unchanged + r.duplicates + r.failed_records === 0 ? (
                  "—"
                ) : (
                  <>
                    <span className="text-ink">{r.records_created}</span> new · {r.records_updated} updated
                    {r.failed_records ? <span className="text-danger"> · {r.failed_records} failed</span> : null}
                  </>
                )}
              </td>
              <td className="max-w-md py-2.5 pl-3 text-2xs text-muted">
                {r.filename ? (
                  <p>
                    {r.filename} · by {r.operator}
                  </p>
                ) : null}
                {r.message}
                {r.errors.length ? <p className="text-danger">{r.errors.length} error(s): {r.errors[0]?.error}</p> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SourcesContent() {
  const me = useMe();
  const qc = useQueryClient();
  const params = useSearchParams();
  const sources = useQuery({ queryKey: ["sources"], queryFn: () => api<SourcesResponse>("/api/v1/sources") });
  const run = useMutation({
    mutationFn: () => api<{ status: string; error: string | null }>("/api/v1/ingestion/run", { method: "POST" }),
    onSuccess: (r) => {
      if (r.status === "succeeded") toast.success("Reanalysis complete");
      else toast.error(`Reanalysis ${r.status}: ${r.error ?? ""}`);
      void qc.invalidateQueries();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const role = me.data?.active_company?.role;

  if (sources.isLoading) return <Skeleton className="h-96 w-full" />;
  if (sources.error || !sources.data) return <ErrorState message="Could not load sources." onRetry={() => void sources.refetch()} />;
  const { schedule, items } = sources.data;

  return (
    <>
      <PageHeader
        title="Data sources"
        description="Where every tender comes from, and what we don't cover yet."
        actions={
          canEdit(role, "admin") ? (
            <Button onClick={() => run.mutate()} disabled={run.isPending}>
              <Play /> {run.isPending ? "Running…" : "Run reanalysis now"}
            </Button>
          ) : null
        }
      />

      <div role="note" className="mb-6 flex gap-3 rounded-2xl border border-warn-line bg-warn-soft px-4 py-3 text-xs text-warn">
        <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
        <p>
          <span className="font-semibold">Partial coverage.</span> No portal here offers a verified public API. TenderOS holds DEMO fixtures plus what your team imports.
          Automated MP eProcurement collection stays off until written authorisation exists.
        </p>
      </div>

      <section aria-labelledby="schedule-title" className="mb-6 grid overflow-hidden rounded-2xl border border-line bg-surface shadow-card md:grid-cols-[1.4fr_1fr_1fr]">
        <div className="p-5">
          <h2 id="schedule-title" className="section-label">
            Scheduled reanalysis
          </h2>
          <p className="mt-2 text-base font-semibold tracking-[-0.01em]">Every 8 hours · {schedule.reanalysis_times_ist.join(" · ")} IST</p>
          <p className="mt-1 text-xs text-muted">Re-checks eligibility, matching and alerts. Collects only from authorised sources.</p>
        </div>
        <div className="border-t border-line p-5 md:border-l md:border-t-0">
          <p className="section-label">Current slot</p>
          <p className="mt-2 font-mono text-xs">{schedule.current_slot}</p>
          <Chip tone={schedule.current_slot_ran ? "ok" : "warn"} className="mt-1.5">
            {schedule.current_slot_ran ? "Completed" : "Not yet run – is the worker running?"}
          </Chip>
        </div>
        <div className="border-t border-line p-5 md:border-l md:border-t-0">
          <p className="section-label">Next</p>
          <p className="mt-2 text-xs">Reanalysis {formatDateTimeIST(schedule.next_reanalysis_at)}</p>
          <p className="mt-0.5 text-xs text-muted">Digest {formatDateTimeIST(schedule.next_digest_at)}</p>
        </div>
        {schedule.recent_jobs.length ? (
          <details className="group border-t border-line md:col-span-3">
            <summary className="cursor-pointer list-none px-5 py-2.5 text-2xs font-medium text-muted hover:text-ink">
              Recent slots ({schedule.recent_jobs.length}) <span className="group-open:hidden">▸</span>
              <span className="hidden group-open:inline">▾</span>
            </summary>
            <ul className="divide-y divide-line border-t border-line px-5 text-xs">
              {schedule.recent_jobs.map((j) => (
                <li key={`${j.job}-${j.slot_key}`} className="flex flex-wrap items-center gap-3 py-2">
                  <span className="w-28 font-medium">{titleCase(j.job)}</span>
                  <span className="font-mono text-2xs text-muted">{j.slot_key}</span>
                  <Chip tone={j.status === "succeeded" ? "ok" : j.status === "running" ? "warn" : "danger"}>{j.status}</Chip>
                  {j.error ? <span className="text-2xs text-danger">{j.error}</span> : null}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </section>

      <div className="space-y-6">
        <Panel title={GROUPS[0]!.title} description={GROUPS[0]!.description}>
          <SourceTable items={items.filter(GROUPS[0]!.test)} />
        </Panel>

        {canEdit(role, "analyst") ? (
          <Panel id="import" title="Import tender" description="Manual, operator-attested import. Imported tenders are private to your company.">
            <ImportPanel
              attestationText={sources.data.attestation_text}
              initialTender={params.get("tender") ?? undefined}
              initialMode={params.get("import") === "document" ? "document" : undefined}
            />
          </Panel>
        ) : null}

        <Panel title="Official portals & references" description="Accessed by people, never scraped. Links open the official site.">
          <div className="grid gap-x-8 md:grid-cols-2">
            {GROUPS.slice(1).map((g) => (
              <ReferenceList key={g.title} title={g.title} items={items.filter(g.test)} />
            ))}
          </div>
        </Panel>

        <Panel title="Recent ingestion jobs" description="Scheduled runs, manual imports and skipped (unauthorised) sources.">
          <Runs />
        </Panel>
      </div>
    </>
  );
}

export default function SourcesPage() {
  return (
    <Suspense>
      <SourcesContent />
    </Suspense>
  );
}
