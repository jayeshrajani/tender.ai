"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CalendarClock, FileWarning, Hourglass, Inbox, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { TenderTable } from "@/components/tenders/tender-table";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/display";
import { api, qs } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDateTimeIST } from "@/lib/format";
import { canEdit, useMe } from "@/lib/hooks";
import type { TenderList } from "@/lib/types";

interface Dashboard {
  counts: { worth_reviewing: number; closing_7d: number; needs_verification: number; deadline_changed_7d: number };
  evidence_gaps: { requirement_type: string; detail: string | null; tenders: number }[];
  generated_at: string;
}

type Mode = "worth" | "closing" | "verify" | "changed";

const MODE_STYLE: Record<Mode, { Icon: typeof Inbox; tile: string }> = {
  worth: { Icon: Sparkles, tile: "bg-accent-soft text-accent" },
  closing: { Icon: Hourglass, tile: "bg-amber-100 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300" },
  verify: { Icon: FileWarning, tile: "bg-rose-100 text-rose-600 dark:bg-rose-400/15 dark:text-rose-300" },
  changed: { Icon: CalendarClock, tile: "bg-violet-100 text-violet-600 dark:bg-violet-400/15 dark:text-violet-300" },
};

function greeting(): string {
  const hour = Number(new Intl.DateTimeFormat("en-IN", { hour: "numeric", hourCycle: "h23", timeZone: "Asia/Kolkata" }).format(new Date()));
  return hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
}

const MODES: { key: Mode; label: string; countKey: keyof Dashboard["counts"]; params: Record<string, string | number | string[]>; explorer: string; hint: string }[] = [
  { key: "worth", label: "Matches worth reviewing", countKey: "worth_reviewing", params: { action: ["review", "verify"], min_score: 50 }, explorer: "action=review&action=verify&min_score=50", hint: "Relevance ≥ 50, not ruled out" },
  { key: "closing", label: "Closing within 7 days", countKey: "closing_7d", params: { action: ["review", "verify"], closing_within: 7, sort: "deadline" }, explorer: "action=review&action=verify&closing_within=7&sort=deadline", hint: "Open, not ruled out" },
  { key: "verify", label: "Missing eligibility evidence", countKey: "needs_verification", params: { action: ["verify"] }, explorer: "action=verify", hint: "Needs verification" },
  { key: "changed", label: "Recently changed deadlines", countKey: "deadline_changed_7d", params: { changed_within: 7, sort: "deadline" }, explorer: "sort=deadline", hint: "Corrigenda in last 7 days" },
];

const GAP_LABEL: Record<string, string> = {
  annual_turnover: "CA-certified turnover",
  similar_work: "Verified completion certificates",
  contractor_registration: "Contractor registration",
  solvency: "Solvency certificate",
  bid_capacity: "Bid capacity calculation",
  equipment: "Equipment proof",
};

function gapLabel(type: string, detail: string | null): string {
  if (type === "certificate" && detail) {
    const map: Record<string, string> = {
      gst: "GST certificate",
      pan: "PAN",
      epf: "EPF registration",
      labour_licence: "Labour licence",
      electrical_licence: "Electrical licence",
      esic: "ESIC registration",
    };
    return map[detail] ?? detail.replace(/_/g, " ");
  }
  return GAP_LABEL[type] ?? type.replace(/_/g, " ");
}

export default function DashboardPage() {
  const me = useMe();
  const [mode, setMode] = useState<Mode>("worth");
  const active = MODES.find((m) => m.key === mode)!;
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: () => api<Dashboard>("/api/v1/dashboard") });
  const list = useQuery({
    queryKey: ["tenders", "dashboard", mode],
    queryFn: () => api<TenderList>(`/api/v1/tenders${qs({ ...active.params, page_size: 15 })}`),
    placeholderData: (prev) => prev,
  });

  return (
    <>
      <PageHeader
        eyebrow={me.data ? `${greeting()}, ${me.data.user.full_name.split(" ")[0]}` : undefined}
        title={me.data?.active_company?.name ?? "Dashboard"}
        description={
          dash.data ? (
            <>
              <span className="font-medium text-ink">{dash.data.counts.worth_reviewing} tenders</span> look worth your time. Scores refreshed{" "}
              {formatDateTimeIST(dash.data.generated_at)}.
            </>
          ) : undefined
        }
        actions={
          <Button asChild variant="primary">
            <Link href="/tenders">
              Explore all tenders <ArrowRight />
            </Link>
          </Button>
        }
      />

      <section aria-label="Quick filters" className="mb-6">
        <div role="tablist" aria-label="Dashboard focus" className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {MODES.map((m) => {
            const selected = m.key === mode;
            const { Icon, tile } = MODE_STYLE[m.key];
            return (
              <button
                key={m.key}
                role="tab"
                aria-selected={selected}
                aria-controls="dashboard-table"
                title={m.hint}
                onClick={() => setMode(m.key)}
                className={cn(
                  "group flex flex-col gap-3 rounded-2xl border bg-surface p-4 text-left shadow-card transition-[transform,box-shadow,border-color] duration-200 ease-snappy hover:-translate-y-0.5 hover:shadow-pop",
                  selected ? "border-accent ring-4 ring-accent/10" : "border-line",
                )}
              >
                <span className="flex items-center justify-between">
                  <span className={cn("grid size-9 place-items-center rounded-xl", tile)}>
                    <Icon className="size-4" aria-hidden />
                  </span>
                  <ArrowRight className={cn("size-4 transition-all duration-200", selected ? "text-accent" : "-translate-x-1 text-faint opacity-0 group-hover:translate-x-0 group-hover:opacity-100")} aria-hidden />
                </span>
                <span>
                  <span className="tabular block font-display text-3xl font-semibold tracking-[-0.03em]">
                    {dash.data ? dash.data.counts[m.countKey] : <Skeleton className="h-8 w-10" />}
                  </span>
                  <span className={cn("mt-0.5 block text-xs", selected ? "font-medium text-ink" : "text-muted")}>{m.label}</span>
                </span>
              </button>
            );
          })}
        </div>
        {dash.data && dash.data.evidence_gaps.length ? (
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-2xl border border-warn-line bg-warn-soft px-4 py-3 text-xs">
            <span className="inline-flex items-center gap-1.5 font-semibold text-warn">
              <FileWarning className="size-4" aria-hidden />
              Unlock more tenders by adding
            </span>
            {dash.data.evidence_gaps.map((g) => (
              <span key={`${g.requirement_type}-${g.detail}`} className="rounded-full bg-surface px-2.5 py-1 text-ink shadow-card">
                {gapLabel(g.requirement_type, g.detail)} <span className="tabular text-muted">· {g.tenders}</span>
              </span>
            ))}
            <Link href="/company/documents" className="ml-auto inline-flex shrink-0 items-center gap-1 font-semibold text-warn hover:underline">
              Open document vault <ArrowRight className="size-3.5" aria-hidden />
            </Link>
          </div>
        ) : null}
      </section>

      {dash.error ? <ErrorState message={dash.error.message} onRetry={() => void dash.refetch()} /> : null}

      <div id="dashboard-table" role="tabpanel" className="overflow-hidden rounded-2xl border border-line bg-surface shadow-card">
        {list.error ? (
          <div className="p-3">
            <ErrorState message={`Could not load tenders: ${list.error.message}`} onRetry={() => void list.refetch()} />
          </div>
        ) : (
          <TenderTable
            rows={list.data?.items}
            loading={list.isFetching}
            canSave={canEdit(me.data?.active_company?.role, "analyst")}
            caption={active.label}
            empty={
              <EmptyState
                icon={Inbox}
                title={mode === "changed" ? "No deadline changes in the last 7 days" : "Nothing here right now"}
                body="TenderOS re-evaluates at 00:00, 08:00 and 16:00 IST. Import tenders from official portals to widen coverage."
                action={
                  <Button asChild>
                    <Link href="/sources#import">Import tender</Link>
                  </Button>
                }
              />
            }
          />
        )}
        {list.data && list.data.total > list.data.items.length ? (
          <div className="border-t border-line px-5 py-3 text-xs">
            <Link href={`/tenders?${active.explorer}`} className="font-medium text-accent hover:underline">
              View all {list.data.total} in explorer →
            </Link>
          </div>
        ) : null}
      </div>
    </>
  );
}
