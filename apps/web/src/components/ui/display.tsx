import { CircleDashed } from "lucide-react";
import type * as React from "react";

import { cn } from "@/lib/cn";
import type { EligibilityStatus, RequirementResult } from "@/lib/types";

type Tone = "neutral" | "accent" | "ok" | "warn" | "danger" | "muted" | "outline";

const tones: Record<Tone, string> = {
  neutral: "bg-subtle text-muted",
  accent: "bg-accent/10 text-accent-ink",
  ok: "bg-ok/10 text-ok",
  warn: "bg-warn/10 text-warn",
  danger: "bg-danger/10 text-danger",
  muted: "bg-subtle/70 text-muted",
  outline: "bg-transparent text-muted ring-1 ring-inset ring-line-strong",
};

export function Chip({
  tone = "neutral",
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex h-[22px] items-center gap-1 whitespace-nowrap rounded-md px-2 text-[11px] font-medium [&_svg]:size-3",
        tones[tone],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
}

const DOT: Record<"ok" | "warn" | "danger" | "muted", string> = {
  ok: "bg-ok",
  warn: "bg-warn",
  danger: "bg-danger",
  muted: "bg-line-strong",
};

export function StatusDot({ tone, children, className }: { tone: keyof typeof DOT; children: React.ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap text-[13px] font-medium text-ink", className)}>
      <span aria-hidden className={cn("size-[7px] shrink-0 rounded-full", DOT[tone])} />
      {children}
    </span>
  );
}

export function DemoBadge({ className }: { className?: string }) {
  return (
    <Chip tone="neutral" className={cn("h-[18px] px-1.5 text-[10px] font-semibold tracking-wide", className)} title="Fictional DEMO record – not a real tender">
      DEMO
    </Chip>
  );
}

const ELIGIBILITY: Record<EligibilityStatus, { label: string; tone: keyof typeof DOT }> = {
  ELIGIBLE: { label: "Eligible", tone: "ok" },
  NEEDS_VERIFICATION: { label: "Needs verification", tone: "warn" },
  NOT_ELIGIBLE: { label: "Not eligible", tone: "danger" },
};

export function EligibilityChip({ status, className }: { status: EligibilityStatus; className?: string }) {
  const { label, tone } = ELIGIBILITY[status];
  return (
    <StatusDot tone={tone} className={className}>
      {label}
    </StatusDot>
  );
}

const RESULT: Record<RequirementResult, { label: string; tone: keyof typeof DOT }> = {
  PASS: { label: "Pass", tone: "ok" },
  FAIL: { label: "Fail", tone: "danger" },
  UNKNOWN: { label: "Needs verification", tone: "warn" },
  NOT_APPLICABLE: { label: "Not applicable", tone: "muted" },
};

export function ResultChip({ result }: { result: RequirementResult }) {
  const { label, tone } = RESULT[result];
  return <StatusDot tone={tone}>{label}</StatusDot>;
}

export function ScoreMeter({ score, className }: { score: number; className?: string }) {
  const pct = Math.max(0, Math.min(100, score));
  return (
    <div className={cn("flex items-center gap-2", className)} title={`Relevance ${pct.toFixed(0)} / 100`}>
      <span className="tabular w-6 text-right text-[13px] font-semibold">{pct.toFixed(0)}</span>
      <span className="relative h-1 w-12 overflow-hidden rounded-full bg-subtle" aria-hidden>
        <span
          className={cn("absolute inset-y-0 left-0 rounded-full", pct >= 70 ? "bg-accent" : pct >= 45 ? "bg-meter-mid" : "bg-line-strong")}
          style={{ width: `${pct}%` }}
        />
      </span>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "block rounded bg-[linear-gradient(90deg,var(--subtle)_0px,var(--raised)_40px,var(--subtle)_80px)] bg-[length:200px_100%] [animation:shimmer_1.4s_linear_infinite]",
        className,
      )}
    />
  );
}

export function EmptyState({
  icon: Icon = CircleDashed,
  title,
  body,
  action,
}: {
  icon?: typeof CircleDashed;
  title: string;
  body?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <span className="mb-4 grid size-12 place-items-center rounded-full bg-subtle text-muted">
        <Icon className="size-5" aria-hidden />
      </span>
      <p className="text-[15px] font-semibold">{title}</p>
      {body ? <p className="mt-1 max-w-md text-[13px] text-muted">{body}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function Panel({
  title,
  description,
  actions,
  className,
  bodyClassName,
  children,
  id,
}: {
  title?: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  children: React.ReactNode;
  id?: string;
}) {
  return (
    <section id={id} className={cn("rounded-[22px] bg-surface", className)} aria-labelledby={title && id ? `${id}-title` : undefined}>
      {title ? (
        <header className="flex items-start justify-between gap-3 px-6 pt-6">
          <div>
            <h2 id={id ? `${id}-title` : undefined} className="text-[17px] font-semibold tracking-[-0.022em]">
              {title}
            </h2>
            {description ? <p className="mt-0.5 text-[13px] text-muted">{description}</p> : null}
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
        </header>
      ) : null}
      <div className={cn("p-6", title && "pt-4", bodyClassName)}>{children}</div>
    </section>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  eyebrow?: string;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 pb-8">
      <div className="min-w-0">
        {eyebrow ? <p className="mb-1 text-[15px] font-semibold text-accent">{eyebrow}</p> : null}
        <h1 className="text-[2rem] font-semibold leading-[1.1] tracking-[-0.025em] md:text-[2.5rem]">{title}</h1>
        {description ? <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function KeyValue({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("min-w-0", className)}>
      <dt className="section-label">{label}</dt>
      <dd className="mt-0.5 text-sm">{children}</dd>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-center justify-between gap-3 rounded-2xl bg-danger/10 px-4 py-3 text-sm text-danger">
      <span>{message}</span>
      {onRetry ? (
        <button type="button" onClick={onRetry} className="font-medium underline underline-offset-4">
          Try again
        </button>
      ) : null}
    </div>
  );
}
