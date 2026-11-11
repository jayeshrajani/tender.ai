/** URL ↔ filter state for the tender explorer. Pure functions so they are unit-testable. */

export const SORTS = ["relevance", "deadline", "value", "published", "title"] as const;
export type Sort = (typeof SORTS)[number];

export interface TenderFilters {
  q: string;
  district: string[];
  category: string[];
  eligibility: string[];
  action: string[];
  closing_within: number | null;
  min_score: number | null;
  saved: boolean;
  include_closed: boolean;
  sort: Sort;
  order: "asc" | "desc" | null;
  page: number;
  page_size: number;
}

export const DEFAULT_FILTERS: TenderFilters = {
  q: "",
  district: [],
  category: [],
  eligibility: [],
  action: [],
  closing_within: null,
  min_score: null,
  saved: false,
  include_closed: false,
  sort: "relevance",
  order: null,
  page: 1,
  page_size: 25,
};

function num(v: string | null): number | null {
  if (v === null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function parseFilters(sp: URLSearchParams): TenderFilters {
  const sort = sp.get("sort");
  const order = sp.get("order");
  return {
    q: sp.get("q") ?? "",
    district: sp.getAll("district"),
    category: sp.getAll("category"),
    eligibility: sp.getAll("eligibility"),
    action: sp.getAll("action"),
    closing_within: num(sp.get("closing_within")),
    min_score: num(sp.get("min_score")),
    saved: sp.get("saved") === "true",
    include_closed: sp.get("include_closed") === "true",
    sort: SORTS.includes(sort as Sort) ? (sort as Sort) : "relevance",
    order: order === "asc" || order === "desc" ? order : null,
    page: Math.max(1, num(sp.get("page")) ?? 1),
    page_size: Math.min(100, Math.max(5, num(sp.get("page_size")) ?? 25)),
  };
}

export function serializeFilters(f: TenderFilters): URLSearchParams {
  const sp = new URLSearchParams();
  if (f.q.trim()) sp.set("q", f.q.trim());
  f.district.forEach((d) => sp.append("district", d));
  f.category.forEach((c) => sp.append("category", c));
  f.eligibility.forEach((e) => sp.append("eligibility", e));
  f.action.forEach((a) => sp.append("action", a));
  if (f.closing_within !== null) sp.set("closing_within", String(f.closing_within));
  if (f.min_score !== null) sp.set("min_score", String(f.min_score));
  if (f.saved) sp.set("saved", "true");
  if (f.include_closed) sp.set("include_closed", "true");
  if (f.sort !== "relevance") sp.set("sort", f.sort);
  if (f.order) sp.set("order", f.order);
  if (f.page > 1) sp.set("page", String(f.page));
  if (f.page_size !== 25) sp.set("page_size", String(f.page_size));
  return sp;
}

/** Changing any filter resets pagination. */
export function updateFilters(f: TenderFilters, patch: Partial<TenderFilters>): TenderFilters {
  const next = { ...f, ...patch };
  if (!("page" in patch)) next.page = 1;
  return next;
}

export function toggleSort(f: TenderFilters, sort: Sort): TenderFilters {
  if (f.sort !== sort) return updateFilters(f, { sort, order: null });
  const current = f.order ?? (sort === "relevance" || sort === "value" || sort === "published" ? "desc" : "asc");
  return updateFilters(f, { order: current === "desc" ? "asc" : "desc" });
}

export function activeFilterCount(f: TenderFilters): number {
  return (
    (f.q.trim() ? 1 : 0) +
    f.district.length +
    f.category.length +
    f.eligibility.length +
    f.action.length +
    (f.closing_within !== null ? 1 : 0) +
    (f.min_score !== null ? 1 : 0) +
    (f.saved ? 1 : 0) +
    (f.include_closed ? 1 : 0)
  );
}
