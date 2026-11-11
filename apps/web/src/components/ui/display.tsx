import { AlertTriangle, CheckCircle2, CircleDashed, CircleSlash, HelpCircle, XCircle } from "lucide-react";
import type * as React from "react";

import { cn } from "@/lib/cn";
import type { EligibilityStatus, RequirementResult } from "@/lib/types";

type Tone = "neutral" | "accent" | "ok" | "warn" | "danger" | "muted" | "outline";

const tones: Record<Tone, string> = {
  neutral: "bg-subtle text-ink border-line",
  accent: "bg-accent-soft text-accent-ink border-accent-line",
  ok: "bg-ok-soft text-ok border-ok-line",
  warn: "bg-warn-soft text-warn border-warn-line",
  danger: "bg-danger-soft text-danger border-danger-line",
  muted: "bg-transparent text-muted border-line",
  outline: "bg-surface text-ink border-line",
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
        "inline-flex h-5 items-center gap-1 whitespace-nowrap rounded-full border px-2 text-2xs font-medium [&_svg]:size-3",
        tones[tone],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
}

export function DemoBadge({ className }: { className?: string }) {
  return (
    <Chip tone="outline" className={cn("font-mono tracking-wide text-muted", className)} title="Fictional DEMO record – not a real tender">
      DEMO
    </Chip>
  );
}

const ELIGIBILITY: Record<EligibilityStatus, { label: string; tone: Tone; Icon: typeof CheckCircle2 }> = {
  ELIGIBLE: { label: "Eligible", tone: "ok", Icon: CheckCircle2 },
  NEEDS_VERIFICATION: { label: "Needs verification", tone: "warn", Icon: AlertTriangle },
  NOT_ELIGIBLE: { label: "Not eligible", tone: "danger", Icon: XCircle },
};

export function EligibilityChip({ status, className }: { status: EligibilityStatus; className?: string }) {
  const { label, tone, Icon } = ELIGIBILITY[status];
  return (
    <Chip tone={tone} className={className}>
      <Icon aria-hidden />
      {label}
    </Chip>
  );
}

const RESULT: Record<RequirementResult, { label: string; tone: Tone; Icon: typeof CheckCircle2 }> = {
  PASS: { label: "PASS", tone: "ok", Icon: CheckCircle2 },
  FAIL: { label: "FAIL", tone: "danger", Icon: XCircle },
  UNKNOWN: { label: "NEEDS VERIFICATION", tone: "warn", Icon: HelpCircle },
  NOT_APPLICABLE: { label: "N/A", tone: "muted", Icon: CircleSlash },
};

export function ResultChip({ result }: { result: RequirementResult }) {
  const { label, tone, Icon } = RESULT[result];
  return (
    <Chip tone={tone} className="font-semibold tracking-wide">
      <Icon aria-hidden />
      {label}
    </Chip>
  );
}

export function ScoreMeter({ score, className }: { score: number; className?: string }) {
  const pct = Math.max(0, Math.min(100, score));
  return (
    <div className={cn("flex items-center gap-2", className)} title={`Relevance ${pct.toFixed(0)} / 100`}>
      <span className="tabular w-6 text-right text-sm font-semibold">{pct.toFixed(0)}</span>
      <span className="relative h-1.5 w-14 overflow-hidden rounded-full bg-subtle" aria-hidden>
        <span
          className={cn("absolute inset-y-0 left-0 rounded-full", pct >= 70 ? "bg-gradient-to-r from-accent to-[#8b5cf6]" : pct >= 45 ? "bg-meter-mid" : "bg-line-strong")}
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
      <span className="mb-4 grid size-12 place-items-center rounded-2xl bg-accent-soft text-accent">
        <Icon className="size-5" aria-hidden />
      </span>
      <p className="font-display text-base font-semibold">{title}</p>
      {body ? <p className="mt-1 max-w-md text-xs text-muted">{body}</p> : null}
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
    <section id={id} className={cn("rounded-2xl border border-line bg-surface shadow-card", className)} aria-labelledby={title && id ? `${id}-title` : undefined}>
      {title ? (
        <header className="flex items-start justify-between gap-3 px-5 pt-5">
          <div>
            <h2 id={id ? `${id}-title` : undefined} className="text-base font-semibold tracking-[-0.01em]">
              {title}
            </h2>
            {description ? <p className="mt-0.5 text-xs text-muted">{description}</p> : null}
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
        </header>
      ) : null}
      <div className={cn("p-5", title && "pt-4", bodyClassName)}>{children}</div>
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
    <div className="flex flex-wrap items-end justify-between gap-3 pb-6">
      <div className="min-w-0">
        {eyebrow ? <p className="mb-1.5 text-sm font-medium text-accent">{eyebrow}</p> : null}
        <h1 className="text-3xl font-semibold tracking-[-0.03em]">{title}</h1>
        {description ? <p className="mt-1.5 max-w-2xl text-sm text-muted">{description}</p> : null}
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
    <div role="alert" className="flex items-center justify-between gap-3 rounded-2xl border border-danger-line bg-danger-soft px-4 py-3 text-sm text-danger">
      <span>{message}</span>
      {onRetry ? (
        <button type="button" onClick={onRetry} className="font-medium underline underline-offset-4">
          Try again
        </button>
      ) : null}
    </div>
  );
}
