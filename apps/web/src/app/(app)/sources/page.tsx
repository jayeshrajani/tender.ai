"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, Info, Lock, Play } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo } from "react";
import { toast } from "sonner";

import UptimeCard, { type Incident, type UptimeService } from "@/components/kokonutui/uptime-card";
import { ImportPanel } from "@/components/sources/import-panel";
import { Button } from "@/components/ui/button";
import { ErrorState, Panel, Skeleton, StatusDot } from "@/components/ui/display";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDateIST, formatDateTimeIST, formatTimeIST, permissionLabel } from "@/lib/format";
import { canEdit, useMe } from "@/lib/hooks";
import type { DayHealth, JobInfo, SourceItem, SourceRun, SourcesResponse } from "@/lib/types";

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
    title: "Qualification & reference",
    description: "Used by people to verify certificates and rates. Not collected.",
    test: (s) => ["qualification_reference", "company_reference", "rate_reference"].includes(s.kind),
  },
  { title: "Messaging", description: "Official Meta WhatsApp Cloud API.", test: (s) => s.kind === "messaging_api" },
];

type Schedule = SourcesResponse["schedule"];

function istMinutesNow(): number {
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date());
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value ?? 0);
  return get("hour") * 60 + get("minute");
}

const toMinutes = (hhmm: string) => {
  const [h = 0, m = 0] = hhmm.split(":").map(Number);
  return h * 60 + m;
};

type SlotState = "done" | "failed" | "running" | "missed" | "upcoming";

function slotState(job: JobInfo | undefined, minute: number, now: number): SlotState {
  if (job) return job.status === "succeeded" ? "done" : job.status === "running" ? "running" : "failed";
  return minute <= now ? "missed" : "upcoming";
}

const SLOT_STYLE: Record<SlotState, { dot: string; label: string }> = {
  done: { dot: "bg-ok ring-ok/25", label: "Ran" },
  failed: { dot: "bg-danger ring-danger/25", label: "Failed" },
  running: { dot: "bg-warn ring-warn/25 animate-pulse", label: "Running" },
  missed: { dot: "bg-surface ring-warn", label: "Not run" },
  upcoming: { dot: "bg-surface ring-line-strong", label: "Upcoming" },
};

/** Today on a 24-hour rail: reanalysis slots, the digest and where we are now. */
function DayRail({ schedule }: { schedule: Schedule }) {
  const now = istMinutesNow();
  const today = schedule.history_end;
  const jobFor = (job: string, hhmm: string) => schedule.recent_jobs.find((j) => j.job === job && j.slot_key === `${today}T${hhmm}+05:30`);
  const marks = [
    ...schedule.reanalysis_times_ist.map((t) => ({ time: t, name: "Reanalysis", job: jobFor("reanalysis", t) })),
    { time: schedule.digest_time_ist, name: "Digest", job: jobFor("daily_digest", schedule.digest_time_ist) },
  ].sort((a, b) => toMinutes(a.time) - toMinutes(b.time));
  const pct = (m: number) => `${(m / 1440) * 100}%`;

  return (
    <div className="mt-4 px-2 pb-1 pt-16 sm:px-4">
      <div className="relative h-[3px] rounded-full bg-subtle">
        <div className="absolute inset-y-0 left-0 rounded-full bg-line-strong" style={{ width: pct(now) }} />
        <div className="absolute -top-8 flex -translate-x-1/2 flex-col items-center" style={{ left: pct(now) }}>
          <span className="rounded-full bg-accent px-1.5 text-[10px] font-semibold leading-4 text-on-accent">Now</span>
          <span className="h-[26px] w-px bg-accent" />
        </div>
        {marks.map((m) => {
          const minute = toMinutes(m.time);
          const state = slotState(m.job, minute, now);
          // Digest sits an hour after a slot, so its label goes above the rail.
          const above = m.name === "Digest";
          const edge = minute < 90 ? "items-start -translate-x-[7px]" : minute > 1350 ? "items-end translate-x-[calc(-100%+7px)]" : "items-center -translate-x-1/2";
          const label = (
            <>
              <span className="tabular text-[13px] font-medium">{m.time}</span>
              <span className="whitespace-nowrap text-[11px] text-muted">
                {m.name} · {SLOT_STYLE[state].label}
              </span>
            </>
          );
          return (
            <div
              key={`${m.name}-${m.time}`}
              className={cn("absolute flex flex-col", edge, above ? "bottom-1/2 translate-y-[7px]" : "top-1/2 -translate-y-[7px]")}
              style={{ left: pct(minute) }}
            >
              {above && Math.abs(now - minute) > 90 ? <div className={cn("mb-2 flex flex-col", edge.split(" ")[0])}>{label}</div> : null}
              <span
                className={cn("size-3.5 rounded-full ring-[3px]", SLOT_STYLE[state].dot)}
                title={`${m.name} ${m.time} IST · ${SLOT_STYLE[state].label}`}
              />
              {above ? null : <div className={cn("mt-2 flex flex-col", edge.split(" ")[0])}>{label}</div>}
            </div>
          );
        })}
      </div>
      <div className="h-14" aria-hidden />
    </div>
  );
}

function StatusHero({ schedule, canRun, running, onRun }: { schedule: Schedule; canRun: boolean; running: boolean; onRun: () => void }) {
  const lastRun = schedule.recent_jobs.find((j) => j.job === "reanalysis" && j.status === "succeeded");
  const failedToday = schedule.reanalysis_history.at(-1) === "down";
  const healthy = schedule.current_slot_ran && !failedToday;
  return (
    <section aria-labelledby="status-title" className="mb-6 overflow-hidden rounded-[28px] bg-surface p-6 sm:p-8">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div className="min-w-0 max-w-2xl">
          <p className="flex items-center gap-2 text-[15px] font-semibold">
            <span className={cn("size-2.5 rounded-full", healthy ? "bg-ok" : "bg-warn")} aria-hidden />
            <span className={healthy ? "text-ok" : "text-warn"}>{healthy ? "On schedule" : "Behind schedule"}</span>
          </p>
          <h1 id="status-title" className="mt-2 text-balance text-[2rem] font-semibold leading-[1.08] tracking-[-0.03em] md:text-[2.75rem]">
            {healthy ? "Tender data is up to date." : failedToday ? "Today's reanalysis failed." : "This slot hasn't run yet."}
          </h1>
          <p className="mt-3 text-[15px] leading-relaxed text-muted">
            {lastRun ? `Last reanalysis ${formatDateTimeIST(lastRun.finished_at ?? lastRun.started_at)}. ` : ""}
            Next at {formatTimeIST(schedule.next_reanalysis_at)} IST, daily digest at {formatTimeIST(schedule.next_digest_at)}.
            {healthy ? "" : " Check that the worker is running."}
          </p>
        </div>
        {canRun ? (
          <Button variant="primary" size="lg" onClick={onRun} disabled={running}>
            <Play /> {running ? "Running…" : "Run reanalysis now"}
          </Button>
        ) : null}
      </div>
      <DayRail schedule={schedule} />
      <p className="mt-2 flex items-start gap-2 border-t border-line pt-4 text-[13px] text-muted">
        <Info className="mt-0.5 size-4 shrink-0 text-faint" aria-hidden />
        <span>
          <span className="font-medium text-ink">Partial coverage.</span> No portal here offers a verified public API. TenderOS holds DEMO fixtures plus what your
          team imports. Automated MP eProcurement collection stays off until written authorisation exists.
        </span>
      </p>
    </section>
  );
}

const INCIDENT: Partial<Record<DayHealth, Incident>> = {
  down: { title: "a run failed", status: "down", minutes: 0, updates: [] },
  degraded: { title: "a run partly failed", status: "degraded", minutes: 0, updates: [] },
};

function toService(name: string, statuses: DayHealth[], note?: string): UptimeService {
  const incidents: Record<number, Incident> = {};
  statuses.forEach((s, i) => {
    const incident = INCIDENT[s];
    if (incident) incidents[i] = incident;
  });
  return { name, statuses, incidents, note };
}

function HealthHistory({ schedule, items }: { schedule: Schedule; items: SourceItem[] }) {
  const services = useMemo(
    () => [
      toService("Scheduled reanalysis", schedule.reanalysis_history),
      ...items.map((s) => toService(s.name, s.history, s.enabled ? undefined : "Off · not authorised")),
    ],
    [schedule.reanalysis_history, items],
  );
  return <UptimeCard title="Last 30 days" okLabel="No failures today" services={services} days={schedule.reanalysis_history.length} endDate={schedule.history_end} className="mb-6" />;
}

const STATE_DOT = (s: SourceItem): "ok" | "warn" | "danger" | "muted" =>
  s.collection_state.startsWith("Disabled") ? "muted" : s.last_run?.status === "failed" ? "danger" : s.last_run?.status === "partial" ? "warn" : "ok";

function CollectionList({ items }: { items: SourceItem[] }) {
  return (
    <section aria-labelledby="collection-title" className="mb-6">
      <h2 id="collection-title" className="mb-3 px-1 text-[22px] font-semibold tracking-[-0.022em]">
        How tenders get in
      </h2>
      <ul className="divide-y divide-line overflow-hidden rounded-[22px] bg-surface">
        {items.map((s) => (
          <li key={s.id} className="grid gap-x-6 gap-y-2 px-6 py-5 md:grid-cols-[minmax(0,1fr)_7rem_11rem] md:items-center">
            <div className="min-w-0">
              <StatusDot tone={STATE_DOT(s)} className="text-[15px] font-semibold">
                {s.name}
              </StatusDot>
              <p className="mt-1 pl-[13px] text-[13px] leading-relaxed text-muted">{s.coverage_note}</p>
              <p className="mt-1 pl-[13px] text-xs text-faint">
                {s.collection_state} · {permissionLabel(s.permission_status)}
                {s.captcha_dependency ? " · CAPTCHA, manual access only" : ""}
              </p>
              {s.last_failure_at ? (
                <p className="mt-1 pl-[13px] text-xs text-danger">
                  Failed {formatDateTimeIST(s.last_failure_at)}: {s.last_error}
                </p>
              ) : null}
            </div>
            <div className="pl-[13px] md:pl-0 md:text-right">
              <p className="tabular text-[22px] font-semibold leading-none tracking-[-0.02em]">{s.tender_count || "—"}</p>
              <p className="mt-1 text-xs text-muted">tenders</p>
            </div>
            <div className="pl-[13px] text-[13px] md:pl-0 md:text-right">
              <p className="text-xs text-muted">Last success</p>
              <p className="tabular mt-0.5">{s.last_success_at ? formatDateTimeIST(s.last_success_at) : <span className="text-faint">Never</span>}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function PortalTiles({ items }: { items: SourceItem[] }) {
  return (
    <section aria-labelledby="portals-title" className="mb-6">
      <h2 id="portals-title" className="mb-1 px-1 text-[22px] font-semibold tracking-[-0.022em]">
        Official portals & references
      </h2>
      <p className="mb-4 px-1 text-[13px] text-muted">Accessed by people, never scraped. Links open the official site.</p>
      <div className="space-y-6">
        {GROUPS.slice(1).map((g) => {
          const list = items.filter(g.test);
          if (!list.length) return null;
          return (
            <div key={g.title}>
              <h3 className="mb-2 px-1 text-[13px] font-medium text-muted">{g.title}</h3>
              <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {list.map((s) => {
                  const linked = s.url && !s.url.includes("{");
                  const body = (
                    <>
                      <div className="flex items-start justify-between gap-3">
                        <p className="text-[15px] font-semibold leading-snug tracking-[-0.01em]">{s.name}</p>
                        {linked ? <ArrowUpRight className="size-4 shrink-0 text-faint transition-colors group-hover:text-accent" aria-hidden /> : null}
                      </div>
                      <p className="mt-1 line-clamp-2 text-[13px] text-muted">{s.coverage_note}</p>
                      <p className="mt-auto flex items-center gap-1.5 pt-3 text-xs text-faint">
                        {s.captcha_dependency ? <Lock className="size-3" aria-label="CAPTCHA – manual access only" /> : null}
                        {s.owner_organization} · {s.api_status}
                      </p>
                    </>
                  );
                  return (
                    <li key={s.id}>
                      {linked ? (
                        <a
                          href={s.url!}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="group flex h-full flex-col rounded-[18px] bg-surface p-5 transition-[transform,box-shadow] duration-200 ease-snappy hover:-translate-y-0.5 hover:shadow-pop"
                        >
                          {body}
                        </a>
                      ) : (
                        <div className="flex h-full flex-col rounded-[18px] bg-surface p-5">{body}</div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </div>
    </section>
  );
}

const RUN_TONE: Record<string, "ok" | "warn" | "danger" | "muted"> = { succeeded: "ok", partial: "warn", failed: "danger", skipped: "muted", running: "warn" };

function ActivityLog() {
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api<{ items: SourceRun[] }>("/api/v1/ingestion/runs") });
  const days = useMemo(() => {
    const by = new Map<string, SourceRun[]>();
    for (const r of runs.data?.items ?? []) {
      const d = formatDateIST(r.started_at);
      by.set(d, [...(by.get(d) ?? []), r]);
    }
    return [...by.entries()];
  }, [runs.data]);

  return (
    <section aria-labelledby="activity-title">
      <h2 id="activity-title" className="mb-1 px-1 text-[22px] font-semibold tracking-[-0.022em]">
        Activity
      </h2>
      <p className="mb-4 px-1 text-[13px] text-muted">Scheduled runs, manual imports and skipped (unauthorised) sources.</p>
      <div className="rounded-[22px] bg-surface px-6 py-5">
        {runs.isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : !days.length ? (
          <p className="text-[13px] text-muted">No ingestion runs yet.</p>
        ) : (
          days.map(([day, list]) => (
            <div key={day} className="mb-5 last:mb-0">
              <h3 className="mb-2 text-[13px] font-semibold">{day}</h3>
              <ol className="relative ml-[3px] border-l border-line">
                {list.map((r) => {
                  const total = r.records_created + r.records_updated + r.records_unchanged + r.duplicates + r.failed_records;
                  return (
                    <li key={r.id} className="relative grid grid-cols-[4.5rem_minmax(0,1fr)] gap-x-3 pb-4 pl-5 last:pb-0">
                      <span
                        aria-hidden
                        className={cn(
                          "absolute -left-[4.5px] top-[7px] size-2 rounded-full ring-4 ring-surface",
                          { ok: "bg-ok", warn: "bg-warn", danger: "bg-danger", muted: "bg-line-strong" }[RUN_TONE[r.status] ?? "muted"],
                        )}
                      />
                      <span className="tabular pt-px text-xs text-faint">{formatTimeIST(r.started_at)}</span>
                      <div className="min-w-0 text-[13px]">
                        <p>
                          <span className="font-medium">{r.source_name}</span>
                          <span className="text-muted">
                            {" "}
                            · <span className="capitalize">{r.status}</span> · {r.trigger}
                            {r.attempt > 1 ? ` · attempt ${r.attempt}` : ""}
                          </span>
                        </p>
                        {total ? (
                          <p className="tabular text-xs text-muted">
                            {r.records_created} new · {r.records_updated} updated · {r.records_unchanged} unchanged
                            {r.failed_records ? <span className="text-danger"> · {r.failed_records} failed</span> : null}
                          </p>
                        ) : null}
                        {r.filename ? (
                          <p className="truncate text-xs text-muted">
                            {r.filename} · by {r.operator}
                          </p>
                        ) : null}
                        {r.message ? <p className="text-xs text-faint">{r.message}</p> : null}
                        {r.errors.length ? (
                          <p className="text-xs text-danger">
                            {r.errors.length} error(s): {r.errors[0]?.error}
                          </p>
                        ) : null}
                      </div>
                    </li>
                  );
                })}
              </ol>
            </div>
          ))
        )}
      </div>
    </section>
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

  if (sources.isLoading) return <Skeleton className="h-96 w-full rounded-[28px]" />;
  if (sources.error || !sources.data) return <ErrorState message="Could not load sources." onRetry={() => void sources.refetch()} />;
  const { schedule, items } = sources.data;
  const collection = items.filter(GROUPS[0]!.test);

  return (
    <div className="mx-auto max-w-5xl">
      <StatusHero schedule={schedule} canRun={canEdit(role, "admin")} running={run.isPending} onRun={() => run.mutate()} />
      <HealthHistory schedule={schedule} items={collection} />
      <CollectionList items={collection} />

      {canEdit(role, "analyst") ? (
        <Panel id="import" title="Import tender" description="Manual, operator-attested import. Imported tenders are private to your company." className="mb-6">
          <ImportPanel
            attestationText={sources.data.attestation_text}
            initialTender={params.get("tender") ?? undefined}
            initialMode={params.get("import") === "document" ? "document" : undefined}
          />
        </Panel>
      ) : null}

      <PortalTiles items={items} />
      <ActivityLog />
    </div>
  );
}

export default function SourcesPage() {
  return (
    <Suspense>
      <SourcesContent />
    </Suspense>
  );
}
