"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download, EyeOff, ExternalLink, FileText, Lock } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { EligibilityMatrix, ScoreBreakdown } from "@/components/tenders/eligibility";
import { CATEGORY_LABEL, DeadlineCell, SaveButton } from "@/components/tenders/tender-table";
import { Button } from "@/components/ui/button";
import { Chip, DemoBadge, EligibilityChip, ErrorState, KeyValue, Panel, Skeleton } from "@/components/ui/display";
import { Textarea } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatBytes, formatDateTimeIST, formatINR, titleCase } from "@/lib/format";
import { canEdit, useMe } from "@/lib/hooks";
import type { TenderDetail, TenderDocument } from "@/lib/types";

function DocumentRow({ tenderId, doc }: { tenderId: string; doc: TenderDocument }) {
  const [busy, setBusy] = useState(false);
  async function open() {
    setBusy(true);
    try {
      const { url } = await api<{ url: string }>(`/api/v1/tenders/${tenderId}/documents/${doc.id}/link`);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not open document");
    } finally {
      setBusy(false);
    }
  }
  return (
    <li className="flex items-start gap-3 py-2.5">
      <FileText className="mt-0.5 size-4 shrink-0 text-faint" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-sm">{doc.title}</p>
        <p className="text-2xs text-muted">
          {titleCase(doc.kind)}
          {doc.page_count ? ` · ${doc.page_count} pages` : ""}
          {doc.size_bytes ? ` · ${formatBytes(doc.size_bytes)}` : ""}
          {doc.extracted_summary?.requirements_extracted !== undefined ? ` · ${doc.extracted_summary.requirements_extracted} criteria extracted` : ""}
          {doc.extracted_summary?.boq ? ` · BOQ ${doc.extracted_summary.boq.item_count} items, ${formatINR(doc.extracted_summary.boq.total_paise)}` : ""}
          {doc.sha256 ? <span className="font-mono"> · sha256 {doc.sha256.slice(0, 10)}…</span> : null}
        </p>
        {doc.extracted_summary?.warnings?.map((w) => (
          <p key={w} className="text-2xs text-warn">
            {w}
          </p>
        ))}
      </div>
      {doc.is_available ? (
        <Button size="sm" onClick={() => void open()} disabled={busy}>
          <Download /> Open
        </Button>
      ) : (
        <Chip tone="muted">Not in TenderOS</Chip>
      )}
    </li>
  );
}

function Notes({ tender, canWrite }: { tender: TenderDetail; canWrite: boolean }) {
  const qc = useQueryClient();
  const [body, setBody] = useState("");
  const add = useMutation({
    mutationFn: () => api(`/api/v1/tenders/${tender.id}/notes`, { method: "POST", json: { body } }),
    onSuccess: () => {
      setBody("");
      void qc.invalidateQueries({ queryKey: ["tender", tender.id] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <div>
      {canWrite ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (body.trim()) add.mutate();
          }}
          className="mb-3"
        >
          <label htmlFor="note" className="sr-only">
            Add internal note
          </label>
          <Textarea id="note" value={body} onChange={(e) => setBody(e.target.value)} placeholder="Internal note for your team (not shared outside your company)" maxLength={4000} />
          <div className="mt-2 flex justify-end">
            <Button type="submit" size="sm" variant="primary" disabled={!body.trim() || add.isPending}>
              Add note
            </Button>
          </div>
        </form>
      ) : null}
      {tender.notes.length === 0 ? (
        <p className="text-xs text-muted">No notes yet.</p>
      ) : (
        <ul className="space-y-3">
          {tender.notes.map((n) => (
            <li key={n.id} className="text-sm">
              <p className="whitespace-pre-wrap">{n.body}</p>
              <p className="mt-0.5 text-2xs text-muted">
                {n.author} · {formatDateTimeIST(n.created_at)}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const RETRIEVAL: Record<string, string> = {
  demo_fixture: "DEMO fixture",
  manual_csv: "Manual CSV import (operator-attested)",
  manual_document: "Manual document import (operator-attested)",
  official_feed: "Authorised official feed",
};

export default function TenderDetailPage() {
  const { id } = useParams<{ id: string }>();
  const me = useMe();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["tender", id], queryFn: () => api<TenderDetail>(`/api/v1/tenders/${id}`) });
  const role = me.data?.active_company?.role;
  const dismiss = useMutation({
    mutationFn: (state: "dismissed" | "none") => api(`/api/v1/tenders/${id}/save`, { method: "POST", json: { state } }),
    onSuccess: (_, state) => {
      toast.success(state === "dismissed" ? "Dismissed – hidden from default views" : "Restored");
      void qc.invalidateQueries({ queryKey: ["tender", id] });
      void qc.invalidateQueries({ queryKey: ["tenders"] });
    },
  });

  if (q.isLoading) {
    return (
      <div className="space-y-3" aria-busy="true">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-7 w-3/4" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (q.error || !q.data) {
    const notFound = q.error instanceof ApiError && q.error.status === 404;
    return (
      <ErrorState
        message={notFound ? "Tender not found, or it is private to another company." : `Could not load tender: ${q.error?.message}`}
        onRetry={notFound ? undefined : () => void q.refetch()}
      />
    );
  }
  const t = q.data;
  const canWrite = canEdit(role, "analyst");

  return (
    <article>
      <nav aria-label="Breadcrumb" className="mb-2 text-xs text-muted">
        <Link href="/tenders" className="inline-flex items-center gap-1 hover:text-ink">
          <ArrowLeft className="size-3.5" aria-hidden /> Tenders
        </Link>
        <span className="mx-1.5">/</span>
        <span className="font-mono">{t.reference_number ?? t.source_tender_id}</span>
      </nav>

      <header className="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 max-w-4xl">
          <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
            {t.is_demo ? <DemoBadge /> : null}
            {t.category_code ? <Chip>{CATEGORY_LABEL[t.category_code] ?? t.category_code}</Chip> : null}
            <Chip tone={t.status === "active" ? "outline" : "muted"}>{titleCase(t.status)}</Chip>
            {t.provenance.is_private_import ? (
              <Chip tone="muted">
                <Lock aria-hidden /> Private to your company
              </Chip>
            ) : null}
            {t.version > 1 ? <Chip tone="warn">Amended · v{t.version}</Chip> : null}
          </div>
          <h1 className="text-2xl font-semibold leading-tight tracking-[-0.025em] md:text-[1.75rem]">{t.title}</h1>
          <p className="mt-1 text-sm text-muted">
            {t.issuing_organization} · {t.department}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SaveButton row={t} disabled={!canWrite} />
          {canWrite ? (
            <Button
              size="sm"
              variant="quiet"
              onClick={() => dismiss.mutate(t.saved_state === "dismissed" ? "none" : "dismissed")}
              disabled={dismiss.isPending}
            >
              <EyeOff /> {t.saved_state === "dismissed" ? "Restore" : "Dismiss"}
            </Button>
          ) : null}
          {t.provenance.source_url ? (
            <Button asChild size="sm">
              <a href={t.provenance.source_url} target="_blank" rel="noopener noreferrer">
                Official portal <ExternalLink />
              </a>
            </Button>
          ) : null}
        </div>
      </header>

      {t.is_demo ? (
        <p className="mb-5 inline-flex items-center gap-1.5 rounded-full bg-subtle px-3 py-1 text-2xs text-muted">
          <span className="font-semibold text-ink">DEMO record.</span> Fictional tender for exploring; the portal link opens the official listing page only.
        </p>
      ) : null}

      <section aria-label="Summary" className="mb-6 grid grid-cols-2 overflow-hidden rounded-2xl border border-line bg-surface shadow-card lg:grid-cols-5">
        <div className="col-span-2 border-b border-line p-5 lg:border-b-0 lg:border-r">
          <p className="section-label mb-2">Eligibility</p>
          <EligibilityChip status={t.eligibility.status} />
          <p className="mt-2 text-xs leading-relaxed text-muted">{t.eligibility.summary}</p>
        </div>
        <div className="border-b border-r border-line p-5 lg:border-b-0">
          <p className="section-label mb-2">Relevance</p>
          <p className="tabular text-2xl font-semibold tracking-[-0.02em]">{t.relevance.score.toFixed(0)}<span className="text-xs font-normal text-muted"> / 100</span></p>
        </div>
        <div className="border-b border-line p-5 lg:border-b-0 lg:border-r">
          <p className="section-label mb-2">Estimated value</p>
          <p className="tabular text-2xl font-semibold tracking-[-0.02em]">{formatINR(t.estimated_value_paise)}</p>
          <p className="tabular text-2xs text-muted">EMD {formatINR(t.emd_paise)}</p>
        </div>
        <div className="col-span-2 p-5 lg:col-span-1">
          <p className="section-label mb-2">Submission deadline</p>
          <DeadlineCell row={t} />
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-6">
          <Panel
            id="eligibility"
            title="Eligibility matrix"
            description={t.eligibility.disclaimer}
            actions={
              t.eligibility.unknown_count ? (
                <Button asChild size="sm">
                  <Link href="/company/documents">Add evidence</Link>
                </Button>
              ) : null
            }
          >
            <EligibilityMatrix tender={t} />
          </Panel>

          <Panel id="nit" title="NIT summary">
            {t.nit_summary ? <p className="text-sm leading-relaxed">{t.nit_summary}</p> : <p className="text-xs text-muted">No summary available from source documents.</p>}
            <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 md:grid-cols-3">
              <KeyValue label="Tender ID">
                <span className="font-mono text-xs">{t.source_tender_id}</span>
              </KeyValue>
              <KeyValue label="Tender type">{t.tender_type ?? "—"}</KeyValue>
              <KeyValue label="Location">{t.location ?? t.district ?? "—"}</KeyValue>
              <KeyValue label="Tender fee">
                <span className="tabular">{formatINR(t.tender_fee_paise)}</span>
              </KeyValue>
              <KeyValue label="Completion period">{t.completion_period_days ? `${Math.round(t.completion_period_days / 30)} months` : "—"}</KeyValue>
              <KeyValue label="Bid opening">{formatDateTimeIST(t.bid_opening_at)}</KeyValue>
            </dl>
          </Panel>

          <Panel id="documents" title="Documents" description="Files are private to your company and opened through short-lived signed links.">
            {t.documents.length ? (
              <ul className="divide-y divide-line">
                {t.documents.map((d) => (
                  <DocumentRow key={d.id} tenderId={t.id} doc={d} />
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted">No documents recorded.</p>
            )}
            {canWrite && t.provenance.is_private_import ? (
              <Button asChild size="sm" className="mt-3">
                <Link href={`/sources?import=document&tender=${t.id}#import`}>Upload NIT / BOQ / corrigendum</Link>
              </Button>
            ) : null}
          </Panel>

          <Panel id="notes" title="Internal review notes">
            <Notes tender={t} canWrite={canWrite} />
          </Panel>
        </div>

        <aside className="space-y-6">
          <Panel title="Relevance breakdown">
            <ScoreBreakdown factors={t.relevance.breakdown} score={t.relevance.score} />
          </Panel>

          <Panel title="Timeline">
            <ol className="relative space-y-3 border-l border-line pl-4">
              {t.timeline.map((e, i) => (
                <li key={`${e.kind}-${i}`} className="relative">
                  <span
                    className={cn(
                      "absolute -left-[21px] top-1 size-2.5 rounded-full border-2 border-surface",
                      e.kind === "corrigendum" || e.kind === "update" ? "bg-warn" : e.kind === "deadline" ? "bg-accent" : "bg-line-strong",
                    )}
                    aria-hidden
                  />
                  <p className="text-xs font-medium">{e.label}</p>
                  <p className="tabular text-2xs text-muted">{formatDateTimeIST(e.at)}</p>
                  {e.note ? <p className="mt-0.5 text-2xs text-muted">{e.note}</p> : null}
                </li>
              ))}
            </ol>
          </Panel>

          {t.versions.length > 1 ? (
            <Panel title="Corrigendum history">
              <ul className="space-y-3">
                {t.versions
                  .filter((v) => v.version > 1)
                  .map((v) => (
                    <li key={v.version} className="text-xs">
                      <p className="font-medium">
                        v{v.version} · {v.corrigendum_ref ?? titleCase(v.change_kind)}
                      </p>
                      <p className="text-2xs text-muted">{formatDateTimeIST(v.captured_at)}</p>
                      <ul className="mt-1 space-y-0.5">
                        {v.changed_fields.map((f) => (
                          <li key={f} className="text-2xs">
                            <span className="text-muted">{titleCase(f)}:</span>{" "}
                            {f.endsWith("_at") && typeof v.previous_values[f] === "string" ? (
                              <span className="line-through decoration-faint">{formatDateTimeIST(v.previous_values[f] as string)}</span>
                            ) : (
                              <span>changed</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </li>
                  ))}
              </ul>
            </Panel>
          ) : null}

          <Panel title="Source & provenance">
            <dl className="space-y-2.5">
              <KeyValue label="Source">{t.provenance.source_name}</KeyValue>
              <KeyValue label="Retrieval method">{RETRIEVAL[t.provenance.retrieval_method] ?? t.provenance.retrieval_method}</KeyValue>
              <KeyValue label="Permission">{titleCase(t.provenance.permission_status)}</KeyValue>
              <KeyValue label="Imported">
                {formatDateTimeIST(t.provenance.imported_at)}
                {t.provenance.imported_by ? ` by ${t.provenance.imported_by}` : ""}
              </KeyValue>
              <KeyValue label="Last confirmed at source">{formatDateTimeIST(t.provenance.last_seen_at)}</KeyValue>
              {t.provenance.original_file_sha256 ? (
                <KeyValue label="Original file SHA-256">
                  <span className="break-all font-mono text-2xs">{t.provenance.original_file_sha256}</span>
                </KeyValue>
              ) : null}
              {t.also_seen_in.length ? (
                <KeyValue label="Also recorded from">
                  <ul>
                    {t.also_seen_in.map((a) => (
                      <li key={a.tender_id}>
                        <Link href={`/tenders/${a.tender_id}`} className="text-accent hover:underline">
                          {a.source}
                        </Link>{" "}
                        <span className="text-2xs text-muted">({RETRIEVAL[a.retrieval_method] ?? a.retrieval_method})</span>
                      </li>
                    ))}
                  </ul>
                </KeyValue>
              ) : null}
            </dl>
          </Panel>
        </aside>
      </div>
    </article>
  );
}
