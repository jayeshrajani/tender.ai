"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ArrowUpDown, CalendarClock, Star } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { Chip, DemoBadge, EligibilityChip, ScoreMeter, Skeleton } from "@/components/ui/display";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { deadlineInfo, formatDateIST, formatINR, formatShortDateIST, formatTimeIST } from "@/lib/format";
import type { Sort } from "@/lib/tender-query";
import type { TenderRow } from "@/lib/types";

export const CATEGORY_LABEL: Record<string, string> = {
  roads: "Roads",
  bridges: "Bridges",
  rcc: "RCC",
  drains: "Drains",
  buildings: "Buildings",
  electrical: "Electrical",
  water_supply: "Water supply",
  sewerage: "Sewerage",
  irrigation: "Irrigation",
  maintenance: "Maintenance",
};

const toneClass = {
  closed: "text-faint",
  urgent: "text-danger font-semibold",
  soon: "text-warn font-medium",
  normal: "text-muted",
  unknown: "text-faint",
} as const;

export function DeadlineCell({ row, now }: { row: Pick<TenderRow, "deadline" | "deadline_changed_at" | "previous_deadline">; now?: Date }) {
  const info = deadlineInfo(row.deadline, now);
  return (
    <div className="leading-tight">
      <div className="tabular whitespace-nowrap text-sm">
        {formatShortDateIST(row.deadline)} <span className="text-2xs text-muted">{formatTimeIST(row.deadline)}</span>
      </div>
      <div className={cn("text-2xs", toneClass[info.tone])}>
        {info.label}
        {row.deadline_changed_at ? (
          <span className="ml-1 inline-flex items-center gap-0.5 text-warn" title={`Changed from ${formatDateIST(row.previous_deadline)}`}>
            <CalendarClock className="size-3" aria-hidden />
            changed
          </span>
        ) : null}
      </div>
    </div>
  );
}

export function SaveButton({ row, disabled }: { row: Pick<TenderRow, "id" | "saved_state" | "title">; disabled?: boolean }) {
  const qc = useQueryClient();
  const saved = row.saved_state === "saved";
  const m = useMutation({
    mutationFn: () => api(`/api/v1/tenders/${row.id}/save`, { method: "POST", json: { state: saved ? "none" : "saved" } }),
    onSuccess: () => {
      toast.success(saved ? "Removed from saved" : "Saved for review");
      void qc.invalidateQueries({ queryKey: ["tenders"] });
      void qc.invalidateQueries({ queryKey: ["tender", row.id] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <button
      type="button"
      onClick={() => m.mutate()}
      disabled={disabled || m.isPending}
      aria-pressed={saved}
      aria-label={saved ? `Unsave ${row.title}` : `Save ${row.title}`}
      title={disabled ? "Viewers cannot save tenders" : saved ? "Saved" : "Save"}
      className="rounded p-1 text-faint transition-colors duration-150 hover:bg-subtle hover:text-ink disabled:opacity-40"
    >
      <Star className={cn("size-4", saved && "fill-accent text-accent")} />
    </button>
  );
}

function SortHeader({
  label,
  sortKey,
  current,
  order,
  onSort,
  align = "left",
  className,
  ariaLabel,
}: {
  label: string;
  sortKey?: Sort;
  current?: Sort;
  order?: "asc" | "desc";
  onSort?: (s: Sort) => void;
  align?: "left" | "right";
  className?: string;
  ariaLabel?: string;
}) {
  if (!sortKey || !onSort)
    return (
      <th scope="col" aria-label={ariaLabel} className={cn("px-3 py-2.5 font-medium", align === "right" && "text-right", className)}>
        {label}
      </th>
    );
  const active = current === sortKey;
  const Icon = !active ? ArrowUpDown : order === "asc" ? ArrowUp : ArrowDown;
  return (
    <th scope="col" aria-label={ariaLabel} aria-sort={active ? (order === "asc" ? "ascending" : "descending") : "none"} className={cn("px-3 py-2.5 font-medium", align === "right" && "text-right", className)}>
      <button
        type="button"
        aria-label={ariaLabel}
        onClick={() => onSort(sortKey)}
        className={cn("inline-flex items-center gap-1 rounded hover:text-ink", active && "text-ink")}
      >
        {label}
        <Icon className={cn("size-3", !active && "opacity-40")} aria-hidden />
      </button>
    </th>
  );
}

export interface TenderTableProps {
  rows: TenderRow[] | undefined;
  loading?: boolean;
  sort?: Sort;
  order?: "asc" | "desc";
  onSort?: (s: Sort) => void;
  canSave?: boolean;
  empty?: React.ReactNode;
  caption: string;
}

export function TenderTable({ rows, loading, sort, order, onSort, canSave = true, empty, caption }: TenderTableProps) {
  if (loading && !rows) return <TableSkeleton />;
  if (rows && rows.length === 0) return <>{empty}</>;
  return (
    <>
      {/* Desktop / tablet: dense table */}
      <div className="hidden overflow-x-auto xl:block">
        <table className="w-full min-w-[900px] border-collapse text-left">
          <caption className="sr-only">{caption}</caption>
          <thead className="whitespace-nowrap border-b border-line text-xs text-muted">
            <tr>
              <th scope="col" className="w-10 px-2 py-2.5">
                <span className="sr-only">Saved</span>
              </th>
              <SortHeader label="Tender" sortKey="title" current={sort} order={order} onSort={onSort} />
              <SortHeader label="Organisation" ariaLabel="Issuing organisation" />
              <SortHeader label="District" className="hidden 2xl:table-cell" />
              <SortHeader label="Est. value" sortKey="value" current={sort} order={order} onSort={onSort} align="right" />
              <SortHeader label="Deadline" ariaLabel="Submission deadline" sortKey="deadline" current={sort} order={order} onSort={onSort} />
              <SortHeader label="Eligibility" />
              <SortHeader label="Relevance" sortKey="relevance" current={sort} order={order} onSort={onSort} />
            </tr>
          </thead>
          <tbody className={cn(loading && "opacity-60 transition-opacity duration-150")}>
            {rows?.map((r) => (
              <tr key={r.id} className="group border-b border-line last:border-0 transition-colors duration-150 hover:bg-raised">
                <td className="py-3.5 pl-3 pr-1 align-top">
                  <SaveButton row={r} disabled={!canSave} />
                </td>
                <td className="min-w-[240px] px-3 py-3.5 align-top">
                  <Link href={`/tenders/${r.id}`} className="line-clamp-2 text-sm font-medium leading-snug text-ink hover:text-accent hover:underline hover:underline-offset-2">
                    {r.title}
                  </Link>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-2xs text-muted">
                    {r.is_demo ? <DemoBadge /> : null}
                    {r.category_code ? <span>{CATEGORY_LABEL[r.category_code] ?? r.category_code}</span> : null}
                    {r.retrieval_method.startsWith("manual") ? <Chip tone="muted">Imported</Chip> : null}
                  </div>
                </td>
                <td className="w-[16%] px-3 py-3.5 align-top text-xs">
                  <div className="line-clamp-2 leading-relaxed text-muted" title={r.department ?? undefined}>
                    {r.issuing_organization ?? "—"}
                  </div>
                  {r.district ? <div className="mt-0.5 text-ink 2xl:hidden">{r.district}</div> : null}
                </td>
                <td className="hidden px-3 py-3.5 align-top text-sm 2xl:table-cell">{r.district ?? "—"}</td>
                <td className="tabular whitespace-nowrap px-3 py-3.5 text-right align-top text-sm font-medium">{formatINR(r.estimated_value_paise)}</td>
                <td className="px-3 py-3.5 align-top">
                  <DeadlineCell row={r} />
                </td>
                <td className="px-3 py-3.5 align-top" title={r.eligibility_summary}>
                  <EligibilityChip status={r.eligibility_status} />
                </td>
                <td className="py-3.5 pl-3 pr-4 align-top">
                  <ScoreMeter score={r.relevance_score} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Narrower screens: stacked summaries */}
      <ul className="divide-y divide-line xl:hidden" aria-label={caption}>
        {rows?.map((r) => (
          <li key={r.id} className="flex gap-2 px-3 py-4 sm:px-4">
            <div className="pt-0.5">
              <SaveButton row={r} disabled={!canSave} />
            </div>
            <div className="min-w-0 flex-1">
              <Link href={`/tenders/${r.id}`} className="line-clamp-2 text-sm font-medium leading-snug hover:text-accent">
                {r.title}
              </Link>
              <p className="mt-1 flex flex-wrap items-center gap-1.5 text-2xs text-muted">
                {r.is_demo ? <DemoBadge /> : null}
                <span className="min-w-0 truncate">
                  {r.issuing_organization} · {r.district ?? "District not stated"}
                </span>
              </p>
              <div className="mt-3 grid grid-cols-[auto_1fr] items-center justify-items-start gap-x-5 gap-y-2 sm:grid-cols-[9rem_5.5rem_minmax(0,1fr)_auto]">
                <EligibilityChip status={r.eligibility_status} />
                <span className="tabular text-sm font-medium">{formatINR(r.estimated_value_paise)}</span>
                <DeadlineCell row={r} />
                <ScoreMeter score={r.relevance_score} className="justify-self-end" />
              </div>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

export function TableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div aria-busy="true" aria-label="Loading tenders" className="divide-y divide-line">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 px-3 py-3.5">
          <Skeleton className="h-4 w-4" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-3/5" />
            <Skeleton className="h-2.5 w-2/5" />
          </div>
          <Skeleton className="hidden h-3 w-32 md:block" />
          <Skeleton className="hidden h-3 w-16 md:block" />
          <Skeleton className="h-3 w-16" />
          <Skeleton className="hidden h-5 w-24 md:block" />
        </div>
      ))}
    </div>
  );
}
