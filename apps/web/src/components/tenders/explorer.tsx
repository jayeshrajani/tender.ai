"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bookmark, ChevronLeft, ChevronRight, SearchX, SlidersHorizontal, Trash2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { toast } from "sonner";

import { ACTION_LABEL, ELIGIBILITY_OPTIONS, MultiSelect, SearchInput, ToggleChip } from "@/components/tenders/filters";
import { CATEGORY_LABEL, TenderTable } from "@/components/tenders/tender-table";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState } from "@/components/ui/display";
import { Popover, PopoverContent, PopoverTrigger, Switch } from "@/components/ui/primitives";
import { api, qs } from "@/lib/api";
import { canEdit, useMe } from "@/lib/hooks";
import { formatDateTimeIST } from "@/lib/format";
import {
  activeFilterCount,
  DEFAULT_FILTERS,
  parseFilters,
  serializeFilters,
  toggleSort,
  updateFilters,
  type TenderFilters,
} from "@/lib/tender-query";
import type { TenderList, TenderRow } from "@/lib/types";

interface Facets {
  districts: { value: string; count: number }[];
  categories: { value: string; count: number }[];
}

function apiParams(f: TenderFilters) {
  return {
    q: f.q,
    district: f.district,
    category: f.category,
    eligibility: f.eligibility,
    action: f.action,
    closing_within: f.closing_within ?? undefined,
    min_score: f.min_score ?? undefined,
    saved: f.saved,
    include_closed: f.include_closed,
    sort: f.sort,
    order: f.order ?? undefined,
    page: f.page,
    page_size: f.page_size,
  };
}

const GROUP_ORDER = ["review", "verify", "not_eligible", "closed", "dismissed"] as const;

function SavedViews({ current }: { current: string }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const views = useQuery({ queryKey: ["views"], queryFn: () => api<{ items: { id: string; name: string; query: string }[] }>("/api/v1/views") });
  const create = useMutation({
    mutationFn: () => api("/api/v1/views", { method: "POST", json: { name, query: current } }),
    onSuccess: () => {
      setName("");
      toast.success("View saved");
      void qc.invalidateQueries({ queryKey: ["views"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/api/v1/views/${id}`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["views"] }),
  });
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button size="sm" className="h-8 rounded-full px-3">
          <Bookmark />
          Saved views
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 p-2">
        <p className="section-label px-1 pb-1">Saved views</p>
        <ul className="mb-2 space-y-px">
          {views.data?.items.map((v) => (
            <li key={v.id} className="group flex items-center gap-1">
              <Link href={`/tenders${v.query ? `?${v.query}` : ""}`} className="flex-1 truncate rounded px-2 py-1.5 text-xs hover:bg-subtle">
                {v.name}
              </Link>
              <button type="button" aria-label={`Delete view ${v.name}`} onClick={() => remove.mutate(v.id)} className="rounded p-1 text-faint opacity-0 hover:text-danger group-hover:opacity-100 focus-visible:opacity-100">
                <Trash2 className="size-3.5" />
              </button>
            </li>
          ))}
          {views.data?.items.length === 0 ? <li className="px-2 py-1.5 text-xs text-muted">No saved views yet.</li> : null}
        </ul>
        <form
          className="flex gap-1.5 border-t border-line pt-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) create.mutate();
          }}
        >
          <label htmlFor="view-name" className="sr-only">
            View name
          </label>
          <input
            id="view-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name this view"
            maxLength={80}
            className="h-7 min-w-0 flex-1 rounded border border-line px-2 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
          />
          <Button type="submit" size="sm" variant="primary" disabled={!name.trim() || create.isPending}>
            Save
          </Button>
        </form>
      </PopoverContent>
    </Popover>
  );
}

export function TenderExplorer() {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const me = useMe();
  const filters = useMemo(() => parseFilters(new URLSearchParams(sp.toString())), [sp]);
  const grouped = sp.get("group") === "action";

  const setFilters = useCallback(
    (next: TenderFilters, extra?: { group?: boolean }) => {
      const params = serializeFilters(next);
      if (extra?.group ?? grouped) params.set("group", "action");
      const s = params.toString();
      router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
    },
    [grouped, pathname, router],
  );
  const patch = (p: Partial<TenderFilters>) => setFilters(updateFilters(filters, p));

  const list = useQuery({
    queryKey: ["tenders", apiParams(filters)],
    queryFn: () => api<TenderList>(`/api/v1/tenders${qs(apiParams(filters))}`),
    placeholderData: (prev) => prev,
  });
  const facets = useQuery({ queryKey: ["facets"], queryFn: () => api<Facets>("/api/v1/tenders/facets"), staleTime: 60_000 });

  const total = list.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / filters.page_size));
  const activeCount = activeFilterCount(filters);
  const canSave = canEdit(me.data?.active_company?.role, "analyst");

  const groups = useMemo(() => {
    if (!grouped || !list.data) return null;
    const by = new Map<string, TenderRow[]>();
    for (const r of list.data.items) by.set(r.action, [...(by.get(r.action) ?? []), r]);
    return GROUP_ORDER.filter((g) => by.has(g)).map((g) => ({ key: g, rows: by.get(g)! }));
  }, [grouped, list.data]);

  const empty = (
    <EmptyState
      icon={SearchX}
      title={activeCount ? "No tenders match these filters" : "No tenders yet"}
      body={
        activeCount
          ? "Try removing a filter. Closed and dismissed tenders are hidden unless you include them."
          : "Import tenders you have accessed on an official portal, or seed the DEMO data."
      }
      action={
        activeCount ? (
          <Button onClick={() => setFilters(DEFAULT_FILTERS, { group: grouped })}>Clear filters</Button>
        ) : (
          <Button asChild variant="primary">
            <Link href="/sources#import">Import tender</Link>
          </Button>
        )
      }
    />
  );

  return (
    <div className="rounded-2xl border border-line bg-surface shadow-card">
      <div className="sticky top-16 z-10 flex flex-wrap items-center gap-2 rounded-t-2xl border-b border-line bg-surface/90 px-4 py-3 backdrop-blur-md">
        <SearchInput value={filters.q} onChange={(q) => patch({ q })} />
        <MultiSelect
          label="District"
          searchable
          options={(facets.data?.districts ?? []).map((d) => ({ value: d.value, label: d.value, count: d.count }))}
          selected={filters.district}
          onChange={(district) => patch({ district })}
        />
        <MultiSelect
          label="Work"
          options={(facets.data?.categories ?? []).map((c) => ({ value: c.value, label: CATEGORY_LABEL[c.value] ?? c.value, count: c.count }))}
          selected={filters.category}
          onChange={(category) => patch({ category })}
        />
        <MultiSelect label="Eligibility" options={ELIGIBILITY_OPTIONS} selected={filters.eligibility} onChange={(eligibility) => patch({ eligibility })} />
        <ToggleChip pressed={filters.closing_within === 7} onClick={() => patch({ closing_within: filters.closing_within === 7 ? null : 7 })}>
          Closing ≤ 7 days
        </ToggleChip>
        <div className="ml-auto flex items-center gap-2">
          {activeCount ? (
            <Button size="sm" variant="quiet" className="h-8 rounded-full px-3" onClick={() => setFilters(DEFAULT_FILTERS, { group: grouped })}>
              Clear ({activeCount})
            </Button>
          ) : null}
          <Popover>
            <PopoverTrigger asChild>
              <Button size="sm" className="h-8 rounded-full px-3">
                <SlidersHorizontal />
                Display
                {filters.saved || filters.include_closed || grouped ? <span className="size-1.5 rounded-full bg-accent" aria-label="options active" /> : null}
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-60 p-2">
              <p className="section-label px-1 pb-1.5">Show</p>
              {(
                [
                  ["Saved tenders only", filters.saved, () => patch({ saved: !filters.saved })],
                  ["Include closed & dismissed", filters.include_closed, () => patch({ include_closed: !filters.include_closed })],
                  ["Group by action needed", grouped, () => setFilters(filters, { group: !grouped })],
                ] as const
              ).map(([label, on, toggle]) => (
                <label key={label} className="flex cursor-pointer items-center justify-between gap-3 rounded-lg px-2 py-2 text-xs hover:bg-subtle">
                  {label}
                  <Switch checked={on} onCheckedChange={toggle} aria-label={label} />
                </label>
              ))}
            </PopoverContent>
          </Popover>
          <SavedViews current={serializeFilters(filters).toString()} />
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 text-2xs text-muted">
        <span aria-live="polite">
          <span className="font-medium text-ink">{list.isFetching && !list.data ? "Loading…" : `${total} tender${total === 1 ? "" : "s"}`}</span>
          {list.data ? ` · computed ${formatDateTimeIST(list.data.generated_at)}` : null}
        </span>
        <span title="TenderOS only holds DEMO fixtures and tenders your team imported.">Partial coverage · DEMO + imported</span>
      </div>

      {list.error ? (
        <div className="p-3">
          <ErrorState message={`Could not load tenders: ${list.error.message}`} onRetry={() => void list.refetch()} />
        </div>
      ) : groups ? (
        groups.length === 0 ? (
          empty
        ) : (
          groups.map((g) => (
            <section key={g.key} aria-labelledby={`group-${g.key}`} className="border-t border-line">
              <div className="flex items-baseline gap-2 bg-subtle/60 px-4 py-2">
                <h3 id={`group-${g.key}`} className="text-xs font-semibold">
                  {ACTION_LABEL[g.key]?.label} <span className="tabular font-normal text-muted">({g.rows.length})</span>
                </h3>
                <span className="text-2xs text-muted">{ACTION_LABEL[g.key]?.description}</span>
              </div>
              <TenderTable rows={g.rows} canSave={canSave} caption={ACTION_LABEL[g.key]?.label ?? g.key} />
            </section>
          ))
        )
      ) : (
        <TenderTable
          rows={list.data?.items}
          loading={list.isFetching}
          sort={filters.sort}
          order={list.data?.order ?? filters.order ?? "desc"}
          onSort={(s) => setFilters(toggleSort(filters, s))}
          canSave={canSave}
          empty={empty}
          caption="Tenders matching your filters"
        />
      )}

      {total > filters.page_size ? (
        <nav aria-label="Pagination" className="flex items-center justify-between border-t border-line px-3 py-2 text-xs">
          <span className="tabular text-muted">
            Page {filters.page} of {pages}
          </span>
          <div className="flex gap-1">
            <Button size="sm" disabled={filters.page <= 1} onClick={() => patch({ page: filters.page - 1 })} aria-label="Previous page">
              <ChevronLeft />
            </Button>
            <Button size="sm" disabled={filters.page >= pages} onClick={() => patch({ page: filters.page + 1 })} aria-label="Next page">
              <ChevronRight />
            </Button>
          </div>
        </nav>
      ) : null}
    </div>
  );
}
