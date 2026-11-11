"use client";

import { useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheet, FileText, Upload } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import FileUpload, { type FileError, type UploadHelpers } from "@/components/kokonutui/file-upload";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/display";
import { Field, Input, Select } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { SourceRun } from "@/lib/types";

interface Preview {
  headers: string[];
  row_count: number;
  sample: Record<string, string>[];
  suggested_mapping: Record<string, string | null>;
  fields: { key: string; label: string; required: boolean }[];
}

interface ImportResult {
  run: SourceRun;
  tender_id?: string;
  warnings?: string[];
  requirements_extracted?: number;
}

const MAX_BYTES = 20 * 1024 * 1024;

const PORTALS = [
  { label: "MP eProcurement – Active tenders", url: "https://mptenders.gov.in/nicgep/app?page=FrontEndLatestActiveTenders&service=page" },
  { label: "MP eProcurement – Advanced search", url: "https://mptenders.gov.in/nicgep/app?page=FrontEndAdvancedSearch&service=page" },
  { label: "MP eProcurement – Corrigenda", url: "https://mptenders.gov.in/nicgep/app?page=FrontEndLatestActiveCorrigendums&service=page" },
  { label: "CPPP", url: "https://eprocure.gov.in/eprocure/app" },
  { label: "GeM BidPlus", url: "https://bidplus.gem.gov.in/all-bids" },
  { label: "MPUDC tenders", url: "https://mpudc.co.in/mptenders.aspx" },
];

function RunResult({ result }: { result: ImportResult }) {
  const { run } = result;
  return (
    <div role="status" className="mt-4 rounded-xl border border-line bg-subtle/50 p-4 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone={run.status === "succeeded" ? "ok" : run.status === "partial" ? "warn" : "danger"} className="uppercase">
          {run.status}
        </Chip>
        <span className="tabular text-muted">
          {run.records_created} created · {run.records_updated} updated · {run.records_unchanged} unchanged · {run.duplicates} duplicates · {run.failed_records} failed
        </span>
      </div>
      {result.requirements_extracted !== undefined ? (
        <p className="mt-2">{result.requirements_extracted} eligibility criteria extracted. Each needs human review before it can confirm eligibility.</p>
      ) : null}
      {result.warnings?.map((w) => (
        <p key={w} className="mt-1 text-warn">
          {w}
        </p>
      ))}
      {run.errors.length ? (
        <ul className="mt-2 max-h-40 space-y-0.5 overflow-y-auto text-danger">
          {run.errors.map((e, i) => (
            <li key={i}>
              {e.row ? `Row ${e.row}: ` : e.record ? `${e.record}: ` : ""}
              {e.error}
            </li>
          ))}
        </ul>
      ) : null}
      {result.tender_id ? (
        <Link href={`/tenders/${result.tender_id}`} className="mt-2 inline-block font-medium text-accent hover:underline">
          Review imported tender →
        </Link>
      ) : null}
    </div>
  );
}

function rethrow(e: unknown): never {
  throw new Error(e instanceof ApiError ? e.message : "Upload failed");
}

export function ImportPanel({ attestationText, initialTender, initialMode }: { attestationText: string; initialTender?: string; initialMode?: "csv" | "document" }) {
  const qc = useQueryClient();
  const [mode, setMode] = useState<"csv" | "document">(initialMode ?? "csv");
  const [attested, setAttested] = useState(false);
  const [portal, setPortal] = useState(PORTALS[0]!.url);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [kind, setKind] = useState("nit");
  const [meta, setMeta] = useState({ source_tender_id: "", title: "", deadline: "", estimated_value: "", corrigendum_ref: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);

  function switchMode(next: "csv" | "document") {
    setMode(next);
    setCsvFile(null);
    setPreview(null);
    setResult(null);
    setError(null);
  }

  function refresh() {
    for (const key of ["runs", "sources", "tenders", "tender", "facets", "dashboard"]) void qc.invalidateQueries({ queryKey: [key] });
  }

  function baseForm(file: File): FormData {
    const body = new FormData();
    body.set("file", file);
    body.set("attestation", "true");
    body.set("source_portal_url", portal);
    return body;
  }

  const requireAttestation = (): FileError | null =>
    attested ? null : { message: "Tick the attestation above first", code: "NOT_ATTESTED" };

  async function uploadCsv(file: File, { onProgress }: UploadHelpers) {
    onProgress(25);
    const body = new FormData();
    body.set("file", file);
    try {
      const p = await api<Preview>("/api/v1/ingestion/csv/preview", { method: "POST", body });
      setCsvFile(file);
      setPreview(p);
      setMapping(p.suggested_mapping);
      setResult(null);
      onProgress(100);
    } catch (e) {
      rethrow(e);
    }
  }

  async function uploadDocument(file: File, { onProgress }: UploadHelpers) {
    onProgress(20);
    const body = baseForm(file);
    body.set("kind", kind);
    if (initialTender) body.set("tender_id", initialTender);
    for (const [k, v] of Object.entries(meta)) if (v.trim()) body.set(k, v.trim());
    try {
      const r = await api<ImportResult>("/api/v1/ingestion/import", { method: "POST", body });
      onProgress(100);
      setResult(r);
      toast.success("Document imported");
      refresh();
    } catch (e) {
      rethrow(e);
    }
  }

  async function importCsv() {
    if (!csvFile || !preview) return;
    const missing = preview.fields.filter((f) => f.required && !mapping[f.key]);
    if (missing.length) return setError(`Map a column to: ${missing.map((m) => m.label).join(", ")}`);
    if (!attested) return setError("Tick the attestation to import");
    setBusy(true);
    setError(null);
    const body = baseForm(csvFile);
    body.set("kind", "csv");
    body.set("mapping", JSON.stringify(mapping));
    try {
      setResult(await api<ImportResult>("/api/v1/ingestion/import", { method: "POST", body }));
      toast.success("Import recorded");
      refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div role="tablist" aria-label="Import type" className="mb-5 inline-flex rounded-xl bg-subtle p-1">
        {(
          [
            ["csv", "Tender list (CSV)", FileSpreadsheet],
            ["document", "NIT / BOQ / corrigendum", FileText],
          ] as const
        ).map(([key, label, Icon]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={mode === key}
            onClick={() => switchMode(key)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs transition-colors duration-150",
              mode === key ? "bg-surface font-medium text-ink shadow-card" : "text-muted hover:text-ink",
            )}
          >
            <Icon className="size-3.5" aria-hidden />
            {label}
          </button>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <div className="space-y-4">
          <p className="text-xs leading-relaxed text-muted">
            Open the official portal, complete any CAPTCHA yourself, download only what you are permitted to use, then upload it here. TenderOS records the file hash, your name
            and the time as provenance, and never bypasses CAPTCHA.
          </p>
          <Field label="Official source" htmlFor="portal" hint="Used as the tender's source link when the file has none.">
            <Select id="portal" value={portal} onChange={(e) => setPortal(e.target.value)}>
              {PORTALS.map((p) => (
                <option key={p.url} value={p.url}>
                  {p.label}
                </option>
              ))}
            </Select>
          </Field>
          <a href={portal} target="_blank" rel="noopener noreferrer" className="inline-block text-xs text-accent hover:underline">
            Open portal in a new tab ↗
          </a>

          {mode === "document" ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Document type" htmlFor="doc-kind">
                <Select id="doc-kind" value={kind} onChange={(e) => setKind(e.target.value)}>
                  <option value="nit">Notice Inviting Tender (NIT)</option>
                  <option value="boq">Bill of Quantities (XLSX)</option>
                  <option value="corrigendum">Corrigendum</option>
                  <option value="other">Other tender document</option>
                </Select>
              </Field>
              {kind === "corrigendum" ? (
                <Field label="Corrigendum reference" htmlFor="m-corr">
                  <Input id="m-corr" value={meta.corrigendum_ref} onChange={(e) => setMeta({ ...meta, corrigendum_ref: e.target.value })} />
                </Field>
              ) : null}
              {initialTender ? (
                <p className="text-xs text-muted sm:col-span-2">
                  Attaching to{" "}
                  <Link href={`/tenders/${initialTender}`} className="text-accent hover:underline">
                    this imported tender
                  </Link>
                  .
                </p>
              ) : (
                <details className="sm:col-span-2">
                  <summary className="cursor-pointer text-xs text-muted hover:text-ink">Details missing from the document? Enter them here</summary>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <Field label="Tender ID" htmlFor="m-id">
                      <Input id="m-id" value={meta.source_tender_id} onChange={(e) => setMeta({ ...meta, source_tender_id: e.target.value })} />
                    </Field>
                    <Field label="Title" htmlFor="m-title">
                      <Input id="m-title" value={meta.title} onChange={(e) => setMeta({ ...meta, title: e.target.value })} />
                    </Field>
                    <Field label="Deadline (IST)" htmlFor="m-deadline" hint="DD-MM-YYYY HH:MM">
                      <Input id="m-deadline" placeholder="28-12-2026 17:30" value={meta.deadline} onChange={(e) => setMeta({ ...meta, deadline: e.target.value })} />
                    </Field>
                    <Field label="Estimated value" htmlFor="m-value" hint="e.g. 3.4 Cr or 85 lakh">
                      <Input id="m-value" value={meta.estimated_value} onChange={(e) => setMeta({ ...meta, estimated_value: e.target.value })} />
                    </Field>
                  </div>
                </details>
              )}
              {kind === "corrigendum" && !initialTender ? (
                <p className="text-2xs text-warn sm:col-span-2">Open the imported tender and use “Upload NIT / BOQ / corrigendum” so the corrigendum is linked to it.</p>
              ) : null}
            </div>
          ) : null}

          <label className="flex items-start gap-2.5 rounded-xl border border-line bg-subtle/40 p-3 text-xs leading-relaxed">
            <Checkbox checked={attested} onCheckedChange={(v) => setAttested(v === true)} aria-label="Attestation" className="mt-0.5" />
            <span>{attestationText}</span>
          </label>
        </div>

        <div>
          <FileUpload
            key={`${mode}-${kind}`}
            className="max-w-none rounded-xl border-line bg-surface dark:border-line dark:bg-surface"
            acceptedFileTypes={mode === "csv" ? [".csv"] : [".pdf", ".xlsx"]}
            maxFileSize={MAX_BYTES}
            multiple={false}
            maxFiles={1}
            validateFile={requireAttestation}
            onUpload={mode === "csv" ? uploadCsv : uploadDocument}
            onUploadError={(err) => toast.error(err.message)}
            onFileRemove={() => {
              if (mode === "csv") {
                setCsvFile(null);
                setPreview(null);
              }
            }}
          />
          <p className="mt-2 text-2xs text-muted">
            {mode === "csv" ? "The CSV is read to suggest column mapping; nothing is imported until you confirm." : "Uploading imports the document and extracts criteria for review."}
          </p>
        </div>
      </div>

      {mode === "csv" && preview ? (
        <div className="mt-6 border-t border-line pt-5">
          <p className="mb-3 text-sm">
            <span className="font-medium">{preview.row_count} rows</span> <span className="text-muted">detected. Check the column mapping:</span>
          </p>
          <div className="grid gap-x-4 gap-y-3 sm:grid-cols-2 lg:grid-cols-4">
            {preview.fields.map((f) => (
              <Field key={f.key} label={f.label} htmlFor={`map-${f.key}`} required={f.required}>
                <Select id={`map-${f.key}`} value={mapping[f.key] ?? ""} onChange={(e) => setMapping({ ...mapping, [f.key]: e.target.value || null })}>
                  <option value="">— not in file —</option>
                  {preview.headers.map((h) => (
                    <option key={h} value={h}>
                      {h}
                    </option>
                  ))}
                </Select>
              </Field>
            ))}
          </div>
          <div className="mt-4 overflow-x-auto rounded-xl border border-line">
            <table className="w-full text-left text-2xs">
              <caption className="sr-only">First rows of the CSV</caption>
              <thead className="bg-subtle text-muted">
                <tr>
                  {preview.headers.map((h) => (
                    <th key={h} scope="col" className="px-3 py-2 font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.sample.map((row, i) => (
                  <tr key={i} className="border-t border-line">
                    {preview.headers.map((h) => (
                      <td key={h} className="max-w-48 truncate px-3 py-2">
                        {row[h]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex items-center justify-end gap-3">
            {error ? (
              <p role="alert" className="text-xs font-medium text-danger">
                {error}
              </p>
            ) : null}
            <Button variant="primary" onClick={() => void importCsv()} disabled={busy}>
              <Upload /> {busy ? "Importing…" : `Import ${preview.row_count} rows`}
            </Button>
          </div>
        </div>
      ) : null}

      {result ? <RunResult result={result} /> : null}
    </div>
  );
}
