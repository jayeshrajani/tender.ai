"use client";

import { Check } from "lucide-react";

import { cn } from "@/lib/cn";

export const STEPS = [
  { n: 1, title: "Business information", hint: "Legal name, type, GST, PAN, contacts" },
  { n: 2, title: "Work categories", hint: "Categories, subcategories, specialties" },
  { n: 3, title: "Geography & project size", hint: "Districts, radius, value range" },
  { n: 4, title: "Financial & technical capacity", hint: "Turnover, experience, class, resources" },
  { n: 5, title: "Certificates & alerts", hint: "Evidence, expiry dates, WhatsApp opt-in" },
] as const;

export function Stepper({ current, completedUpTo, onSelect }: { current: number; completedUpTo: number; onSelect: (n: number) => void }) {
  return (
    <ol className="space-y-1" aria-label="Setup steps">
      {STEPS.map((s) => {
        const done = s.n < completedUpTo;
        const active = s.n === current;
        const reachable = s.n <= completedUpTo;
        return (
          <li key={s.n}>
            <button
              type="button"
              onClick={() => reachable && onSelect(s.n)}
              disabled={!reachable}
              aria-current={active ? "step" : undefined}
              className={cn(
                "flex w-full items-start gap-3 rounded-md px-2.5 py-2 text-left transition-colors duration-150",
                active ? "bg-surface shadow-card ring-1 ring-line" : reachable ? "hover:bg-subtle" : "opacity-50",
              )}
            >
              <span
                className={cn(
                  "mt-0.5 grid size-5 shrink-0 place-items-center rounded-full border text-2xs font-semibold",
                  done ? "border-accent bg-accent text-on-accent" : active ? "border-accent text-accent" : "border-line-strong text-muted",
                )}
              >
                {done ? <Check className="size-3" strokeWidth={3} aria-hidden /> : s.n}
              </span>
              <span>
                <span className={cn("block text-xs font-medium", active ? "text-ink" : "text-muted")}>{s.title}</span>
                <span className="block text-2xs text-faint">{s.hint}</span>
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
