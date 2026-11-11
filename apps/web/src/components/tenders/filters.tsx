"use client";

import { Check, ChevronDown, Search, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox, Popover, PopoverContent, PopoverTrigger } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";

export interface Option {
  value: string;
  label: string;
  count?: number;
}

export function MultiSelect({
  label,
  options,
  selected,
  onChange,
  searchable,
}: {
  label: string;
  options: Option[];
  selected: string[];
  onChange: (v: string[]) => void;
  searchable?: boolean;
}) {
  const [filter, setFilter] = useState("");
  const visible = options.filter((o) => o.label.toLowerCase().includes(filter.toLowerCase()));
  const toggle = (v: string) => onChange(selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v]);
  const summary =
    selected.length === 0 ? null : selected.length === 1 ? options.find((o) => o.value === selected[0])?.label ?? selected[0] : `${selected.length} selected`;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-xs transition-colors duration-150",
            selected.length ? "border-accent/40 bg-accent-soft text-accent-ink" : "border-line bg-surface text-ink hover:border-line-strong",
          )}
        >
          <span className="text-muted">{label}</span>
          {summary ? <span className="max-w-32 truncate font-medium">{summary}</span> : null}
          <ChevronDown className="size-3.5 text-muted" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-60">
        {searchable ? (
          <div className="relative mb-1">
            <Search className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-faint" aria-hidden />
            <input
              aria-label={`Filter ${label}`}
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder={`Find ${label.toLowerCase()}`}
              className="h-7 w-full rounded border border-line pl-7 pr-2 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
            />
          </div>
        ) : null}
        <ul role="listbox" aria-label={label} aria-multiselectable className="max-h-64 overflow-y-auto">
          {visible.map((o) => {
            const id = `ms-${label}-${o.value}`.replace(/\s+/g, "-");
            return (
              <li key={o.value}>
                <label htmlFor={id} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-xs hover:bg-subtle">
                  <Checkbox id={id} checked={selected.includes(o.value)} onCheckedChange={() => toggle(o.value)} />
                  <span className="flex-1">{o.label}</span>
                  {o.count !== undefined ? <span className="tabular text-2xs text-muted">{o.count}</span> : null}
                </label>
              </li>
            );
          })}
          {visible.length === 0 ? <li className="px-2 py-2 text-xs text-muted">No matches</li> : null}
        </ul>
        {selected.length ? (
          <div className="mt-1 border-t border-line pt-1">
            <Button variant="quiet" size="sm" className="w-full" onClick={() => onChange([])}>
              Clear {label.toLowerCase()}
            </Button>
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}

export function ToggleChip({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(
        "inline-flex h-8 items-center gap-1 rounded-full border px-3 text-xs transition-colors duration-150",
        pressed ? "border-accent/40 bg-accent-soft font-medium text-accent-ink" : "border-line bg-surface text-ink hover:border-line-strong",
      )}
    >
      {pressed ? <Check className="size-3.5" aria-hidden /> : null}
      {children}
    </button>
  );
}

export function SearchInput({ value, onChange, label = "Search tenders" }: { value: string; onChange: (v: string) => void; label?: string }) {
  const [local, setLocal] = useState(value);
  const [prev, setPrev] = useState(value);
  if (value !== prev) {
    // URL changed externally (back button, clear filters): adopt it.
    setPrev(value);
    setLocal(value);
  }
  useEffect(() => {
    if (local === value) return;
    const t = setTimeout(() => onChange(local), 250);
    return () => clearTimeout(t);
  }, [local, value, onChange]);
  return (
    <div className="relative w-full sm:w-64">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-faint" aria-hidden />
      <label htmlFor="tender-search" className="sr-only">
        {label}
      </label>
      <input
        id="tender-search"
        type="search"
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        placeholder="Title, department, NIT no."
        className="h-8 w-full rounded-full border border-line bg-surface pl-8 pr-7 text-xs placeholder:text-faint hover:border-line-strong focus-visible:border-accent focus-visible:outline-none"
      />
      {local ? (
        <button type="button" aria-label="Clear search" onClick={() => { setLocal(""); onChange(""); }} className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-faint hover:text-ink">
          <X className="size-3.5" />
        </button>
      ) : null}
    </div>
  );
}

export const ELIGIBILITY_OPTIONS: Option[] = [
  { value: "ELIGIBLE", label: "Eligible" },
  { value: "NEEDS_VERIFICATION", label: "Needs verification" },
  { value: "NOT_ELIGIBLE", label: "Not eligible" },
];

export const ACTION_LABEL: Record<string, { label: string; description: string }> = {
  review: { label: "Ready to review", description: "All mandatory criteria met with verified evidence" },
  verify: { label: "Verify evidence", description: "Missing, unverified or expired evidence – or criteria awaiting review" },
  not_eligible: { label: "Not eligible", description: "A confirmed mandatory criterion fails" },
  closed: { label: "Closed", description: "Submission deadline passed or tender not active" },
  dismissed: { label: "Dismissed", description: "Hidden by your team" },
};
