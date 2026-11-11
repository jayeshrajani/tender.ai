"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, FileText, Quote, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Chip, ResultChip } from "@/components/ui/display";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { RequirementRow, ScoreFactor, TenderDetail } from "@/lib/types";

function EvidenceList({ items }: { items: RequirementRow["company_evidence"] }) {
  if (!items.length) return null;
  return (
    <ul className="mt-2 divide-y divide-line rounded-lg border border-line">
      {items.map((e, i) => (
        <li key={`${e.kind}-${e.id ?? e.field}-${i}`} className="flex items-center gap-3 px-3 py-1.5 text-xs">
          <span className="w-20 shrink-0 text-2xs capitalize text-faint">{e.kind}</span>
          <span className="min-w-0 flex-1 text-ink">{e.title ?? e.value}</span>
          {e.kind === "experience" && e.value ? <span className="tabular shrink-0 text-muted">{e.value}</span> : null}
          {e.kind === "certificate" ? (
            <Chip tone={e.verification_status === "verified" ? "ok" : "warn"} className="shrink-0 capitalize">
              {e.verification_status}
            </Chip>
          ) : null}
          {e.kind === "experience" && e.certificate_verified === false ? (
            <Chip tone="warn" className="shrink-0">
              Certificate unverified
            </Chip>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function ReviewControls({ tenderId, req }: { tenderId: string; req: RequirementRow }) {
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: (verification_status: string) =>
      api(`/api/v1/tenders/${tenderId}/requirements/${req.id}`, { method: "PATCH", json: { verification_status } }),
    onSuccess: () => {
      toast.success("Criterion reviewed; eligibility recomputed");
      void qc.invalidateQueries({ queryKey: ["tender", tenderId] });
      void qc.invalidateQueries({ queryKey: ["tenders"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  if (req.verification_status === "source_verified") return null;
  return (
    <div className="mt-3 flex gap-1.5">
      <Button size="sm" onClick={() => m.mutate("source_verified")} disabled={m.isPending}>
        <Check /> Confirm against NIT
      </Button>
      {req.verification_status !== "rejected" ? (
        <Button size="sm" variant="quiet" onClick={() => m.mutate("rejected")} disabled={m.isPending}>
          <X /> Reject
        </Button>
      ) : null}
    </div>
  );
}

export function EligibilityMatrix({ tender }: { tender: TenderDetail }) {
  const reqs = tender.eligibility.requirements;
  if (!reqs.length) {
    return (
      <div className="rounded-md border border-dashed border-line-strong bg-subtle/50 px-4 py-6 text-center">
        <p className="text-sm font-medium">No eligibility criteria extracted</p>
        <p className="mx-auto mt-1 max-w-md text-xs text-muted">
          {tender.documents_available
            ? "The uploaded documents did not contain recognisable criteria. Review the NIT manually."
            : "The NIT is not available in TenderOS. Download it from the official portal and import it to extract criteria with page citations."}{" "}
          TenderOS does not guess criteria without a source document.
        </p>
      </div>
    );
  }
  return (
    <ul aria-label="Eligibility criteria with evidence and citations" className="divide-y divide-line">
      {reqs.map((r) => (
        <li key={r.id} className={cn("py-4 first:pt-0 last:pb-0", r.verification_status === "rejected" && "opacity-60")}>
          <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
            <div className="min-w-0 flex-1">
              <h3 className="text-sm font-medium leading-snug">{r.label}</h3>
              <div className="mt-1.5 flex flex-wrap gap-1">
                {r.mandatory ? <Chip tone="outline">Mandatory</Chip> : <Chip tone="muted">Informational</Chip>}
                {r.verification_status === "needs_review" ? (
                  <Chip tone="warn" title="Extracted automatically; confirm against the NIT">
                    Awaiting review
                  </Chip>
                ) : null}
                {r.verification_status === "rejected" ? <Chip tone="muted">Rejected</Chip> : null}
              </div>
            </div>
            <ResultChip result={r.result} />
          </div>

          <div className="mt-3 grid gap-4 md:grid-cols-2">
            <div className="min-w-0 text-xs">
              <p className="section-label mb-1">Your evidence</p>
              <p className="leading-relaxed text-ink">{r.explanation}</p>
              <EvidenceList items={r.company_evidence} />
            </div>
            <div className="min-w-0 text-xs">
              <p className="section-label mb-1">Source</p>
              <p className="flex items-center gap-1.5 text-ink">
                <FileText className="size-3.5 shrink-0 text-faint" aria-hidden />
                <span className="truncate">{r.citation.document ?? "Document not recorded"}</span>
              </p>
              <p className="mt-0.5 text-2xs text-muted">
                {r.citation.page ? `Page ${r.citation.page}` : "Page not recorded"}
                {r.citation.clause ? ` · Clause ${r.citation.clause}` : ""}
                {` · ${r.extraction_method === "seed" ? "DEMO fixture" : r.extraction_method}`}
              </p>
              {r.citation.quote ? (
                <blockquote className="mt-2 flex gap-2 rounded-lg bg-subtle/60 px-3 py-2 text-2xs leading-relaxed text-ink/85" lang="hi-IN en-IN">
                  <Quote className="mt-0.5 size-3 shrink-0 text-faint" aria-hidden />
                  {r.citation.quote}
                </blockquote>
              ) : null}
            </div>
          </div>
          {tender.can_review_requirements ? <ReviewControls tenderId={tender.id} req={r} /> : null}
        </li>
      ))}
    </ul>
  );
}

export function ScoreBreakdown({ factors, score }: { factors: ScoreFactor[]; score: number }) {
  return (
    <div>
      <div className="mb-3 flex items-baseline gap-2">
        <span className="tabular text-2xl font-semibold">{score.toFixed(0)}</span>
        <span className="text-xs text-muted">/ 100 relevance · independent of eligibility</span>
      </div>
      <ul className="space-y-2.5">
        {factors.map((f) => (
          <li key={f.key}>
            <div className="flex items-baseline justify-between gap-2 text-xs">
              <span className="font-medium">{f.label}</span>
              <span className="tabular text-muted">
                <span className="font-semibold text-ink">{f.points.toFixed(1)}</span> / {f.weight}
              </span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-subtle" aria-hidden>
              <div className="h-full rounded-full bg-accent" style={{ width: `${f.fraction * 100}%` }} />
            </div>
            <p className="mt-0.5 text-2xs text-muted">{f.reason}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
