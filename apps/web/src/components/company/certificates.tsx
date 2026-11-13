"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Award,
  BadgeCheck,
  Download,
  Factory,
  FileText,
  HardHat,
  HeartPulse,
  IdCard,
  Landmark,
  type LucideIcon,
  Plus,
  Receipt,
  ShieldCheck,
  Trash2,
  TrendingUp,
  Upload,
  Users,
  Zap,
} from "lucide-react";
import { Fragment, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Chip, StatusDot } from "@/components/ui/display";
import { Field, Input, Select } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatBytes, formatDateIST, formatINR, toPaise } from "@/lib/format";
import { useReference } from "@/lib/hooks";
import type { Certificate } from "@/lib/types";

const ALLOWED = ["application/pdf", "image/jpeg", "image/png"];
const MAX_MB = 20;

export function validateCertificateFile(file: File | null): string | null {
  if (!file) return null;
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!["pdf", "jpg", "jpeg", "png"].includes(ext) || (file.type && !ALLOWED.includes(file.type))) {
    return "Only PDF, JPG or PNG files are accepted.";
  }
  if (file.size > MAX_MB * 1024 * 1024) return `File exceeds ${MAX_MB} MB.`;
  if (file.size === 0) return "The file is empty.";
  return null;
}

function invalidate(qc: ReturnType<typeof useQueryClient>) {
  void qc.invalidateQueries({ queryKey: ["profile"] });
  void qc.invalidateQueries({ queryKey: ["documents"] });
  void qc.invalidateQueries({ queryKey: ["tenders"] });
  void qc.invalidateQueries({ queryKey: ["tender"] });
  void qc.invalidateQueries({ queryKey: ["dashboard"] });
}

export function CertificateForm({ onDone, existing }: { onDone?: () => void; existing?: Certificate }) {
  const ref = useReference();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [type, setType] = useState(existing?.cert_type ?? "gst");
  const [title, setTitle] = useState(existing?.title ?? "");
  const [number, setNumber] = useState(existing?.number ?? "");
  const [issuer, setIssuer] = useState(existing?.issuer ?? "");
  const [expires, setExpires] = useState(existing?.expires_on ?? "");
  const [cls, setCls] = useState(existing?.registration_class ?? "");
  const [value, setValue] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (title.trim().length < 2) errs.title = "Enter a title";
    const fileErr = validateCertificateFile(file);
    if (fileErr) errs.file = fileErr;
    if (value && !(Number(value) > 0)) errs.value = "Enter an amount in lakh";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    const body = new FormData();
    body.set("cert_type", type);
    body.set("title", title.trim());
    if (number) body.set("number", number);
    if (issuer) body.set("issuer", issuer);
    if (expires) body.set("expires_on", expires);
    if (cls) body.set("registration_class", cls);
    if (value) body.set("value_paise", String(toPaise(Number(value), "lakh")));
    if (existing) body.set("certificate_id", existing.id);
    if (file) body.set("file", file);
    setBusy(true);
    try {
      await api("/api/v1/company/documents", { method: "POST", body });
      toast.success(file ? "Uploaded – awaiting verification" : "Certificate saved");
      invalidate(qc);
      onDone?.();
    } catch (err) {
      if (err instanceof ApiError) setErrors({ ...err.fieldErrors, form: err.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="grid gap-3 md:grid-cols-2">
      <Field label="Certificate type" htmlFor="cert-type" required>
        <Select id="cert-type" value={type} onChange={(e) => setType(e.target.value)} disabled={!!existing}>
          {ref.data?.certificate_types.map((t) => (
            <option key={t.code} value={t.code}>
              {t.label}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Title" htmlFor="cert-title" error={errors.title} required>
        <Input id="cert-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. MP PWD registration – Class B" />
      </Field>
      <Field label="Certificate number" htmlFor="cert-number">
        <Input id="cert-number" value={number} onChange={(e) => setNumber(e.target.value)} />
      </Field>
      <Field label="Issued by" htmlFor="cert-issuer">
        <Input id="cert-issuer" value={issuer} onChange={(e) => setIssuer(e.target.value)} />
      </Field>
      <Field label="Expiry date" htmlFor="cert-expiry" hint="Expired certificates never count as evidence." error={errors.expires_on}>
        <Input id="cert-expiry" type="date" value={expires} onChange={(e) => setExpires(e.target.value)} />
      </Field>
      {type === "contractor_registration" ? (
        <Field label="Registration class" htmlFor="cert-class">
          <Select id="cert-class" value={cls} onChange={(e) => setCls(e.target.value)}>
            <option value="">—</option>
            {ref.data?.registration_classes.map((c) => (
              <option key={c} value={c}>
                Class {c}
              </option>
            ))}
          </Select>
        </Field>
      ) : null}
      {type === "solvency" ? (
        <Field label="Solvency amount (₹ lakh)" htmlFor="cert-value" error={errors.value}>
          <Input id="cert-value" inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} />
        </Field>
      ) : null}
      <Field label="File (PDF, JPG or PNG, max 20 MB)" htmlFor="cert-file" error={errors.file} className="md:col-span-2">
        <input
          ref={fileRef}
          id="cert-file"
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
          onChange={(e) => {
            const f = e.target.files?.[0] ?? null;
            setFile(f);
            setErrors((x) => ({ ...x, file: validateCertificateFile(f) ?? "" }));
          }}
          className="block w-full text-[13px] text-muted file:mr-3 file:h-8 file:rounded-full file:border-0 file:bg-subtle file:px-4 file:text-[13px] file:font-medium file:text-ink hover:file:bg-line"
        />
      </Field>
      {errors.form ? (
        <p role="alert" className="text-xs text-danger md:col-span-2">
          {errors.form}
        </p>
      ) : null}
      <div className="flex justify-end gap-2 md:col-span-2">
        {onDone ? (
          <Button variant="quiet" onClick={onDone}>
            Cancel
          </Button>
        ) : null}
        <Button type="submit" variant="primary" disabled={busy}>
          <Upload /> {busy ? "Uploading…" : existing ? "Replace file" : "Save certificate"}
        </Button>
      </div>
    </form>
  );
}

const EXPIRY_CHIP = {
  expired: { tone: "danger" as const, label: "Expired" },
  expiring: { tone: "warn" as const, label: "Renew soon" },
  valid: { tone: "muted" as const, label: "Valid" },
  none: { tone: "muted" as const, label: "No expiry" },
};

function useCertificateActions() {
  const qc = useQueryClient();
  const verify = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api(`/api/v1/company/certificates/${id}/verification`, { method: "PATCH", json: { verification_status: status } }),
    onSuccess: () => {
      toast.success("Verification updated; eligibility recomputed");
      invalidate(qc);
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/api/v1/company/certificates/${id}`, { method: "DELETE" }),
    onSuccess: () => invalidate(qc),
  });
  async function open(docId: string) {
    try {
      const { url } = await api<{ url: string }>(`/api/v1/company/documents/${docId}/link`);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not open file");
    }
  }
  return { verify, remove, open };
}

/* Settings-app style glyph colours (Apple system palette). */
const TYPE_STYLE: Record<string, { color: string; Icon: LucideIcon }> = {
  contractor_registration: { color: "#0a84ff", Icon: HardHat },
  gst: { color: "#5e5ce6", Icon: Receipt },
  pan: { color: "#64d2ff", Icon: IdCard },
  turnover_certificate: { color: "#30d158", Icon: TrendingUp },
  solvency: { color: "#34c759", Icon: Landmark },
  experience: { color: "#ff9f0a", Icon: Award },
  epf: { color: "#ff375f", Icon: Users },
  esic: { color: "#ff453a", Icon: HeartPulse },
  labour_licence: { color: "#bf5af2", Icon: BadgeCheck },
  electrical_licence: { color: "#ffd60a", Icon: Zap },
  udyam: { color: "#ac8e68", Icon: Factory },
  iso: { color: "#8e8e93", Icon: ShieldCheck },
};
const OTHER_STYLE = { color: "#8e8e93", Icon: FileText };

const VERIFY_DOT = {
  verified: { tone: "ok" as const, label: "Verified" },
  unverified: { tone: "warn" as const, label: "Unverified" },
  rejected: { tone: "danger" as const, label: "Rejected" },
};

function WalletCard({ c, canManage, onReplace }: { c: Certificate; canManage: boolean; onReplace: () => void }) {
  const { verify, remove, open } = useCertificateActions();
  const { color, Icon } = TYPE_STYLE[c.cert_type] ?? OTHER_STYLE;
  const v = VERIFY_DOT[c.verification_status];
  const detail = [c.registration_class ? `Class ${c.registration_class}` : null, c.value_paise ? formatINR(c.value_paise) : null, c.issuer].filter(Boolean).join(" · ");
  return (
    <article aria-label={c.title} className="flex w-full flex-col rounded-[22px] bg-surface p-5">
      <div className="flex items-start justify-between gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-[11px] text-white" style={{ background: color }}>
          <Icon className="size-5" strokeWidth={1.75} aria-hidden />
        </span>
        <StatusDot tone={v.tone}>{v.label}</StatusDot>
      </div>
      <p className="mt-4 text-xs text-muted">{c.type_label}</p>
      <h3 className="mt-0.5 text-[17px] font-semibold leading-snug tracking-[-0.022em]">{c.title}</h3>
      {c.number ? <p className="mt-1 truncate font-mono text-[13px] text-muted">{c.number}</p> : null}
      {detail ? <p className="mt-0.5 truncate text-[13px] text-muted">{detail}</p> : null}

      <div className="min-h-5 flex-1" aria-hidden />
      <dl className="grid grid-cols-2 gap-3 border-t border-line pt-4 text-[13px]">
        <div>
          <dt className="text-xs text-muted">Expires</dt>
          <dd className={cn("tabular mt-0.5 font-medium", c.expiry_state === "expired" ? "text-danger" : c.expiry_state === "expiring" ? "text-warn" : "")}>
            {c.expires_on ? formatDateIST(c.expires_on) : "No expiry"}
            {c.expiry_state === "expired" || c.expiry_state === "expiring" ? <span className="block text-xs font-normal">{EXPIRY_CHIP[c.expiry_state].label}</span> : null}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-xs text-muted">File</dt>
          <dd className="mt-0.5">
            {c.document ? (
              <button type="button" onClick={() => void open(c.document!.id)} className="block max-w-full truncate font-medium text-accent hover:underline" title={c.document.filename}>
                {c.document.filename}
              </button>
            ) : (
              <span className="font-medium text-danger">Missing</span>
            )}
            {c.document ? <span className="block text-xs text-muted">{formatBytes(c.document.size_bytes)}</span> : null}
          </dd>
        </div>
      </dl>

      {canManage ? (
        <div className="mt-4 flex items-center gap-1">
          {c.verification_status !== "verified" && c.document ? (
            <Button size="sm" variant="primary" onClick={() => verify.mutate({ id: c.id, status: "verified" })} title="Confirm you checked the original against the issuing authority">
              Mark verified
            </Button>
          ) : null}
          {c.verification_status === "verified" ? (
            <Button size="sm" onClick={() => verify.mutate({ id: c.id, status: "unverified" })}>
              Unverify
            </Button>
          ) : null}
          <span className="flex-1" />
          <Button size="icon" variant="quiet" aria-label={`${c.document ? "Replace file for" : "Upload file for"} ${c.title}`} title={c.document ? "Replace file" : "Upload file"} onClick={onReplace}>
            <Upload />
          </Button>
          <Button size="icon" variant="quiet" aria-label={`Delete ${c.title}`} title="Delete" onClick={() => remove.mutate(c.id)}>
            <Trash2 />
          </Button>
        </div>
      ) : null}
    </article>
  );
}

export function CertificateWallet({
  certificates,
  canManage,
  onAdd,
  onReplace,
}: {
  certificates: Certificate[];
  canManage: boolean;
  onAdd?: () => void;
  onReplace: (c: Certificate) => void;
}) {
  return (
    <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {certificates.map((c) => (
        <li key={c.id} className="flex">
          <WalletCard c={c} canManage={canManage} onReplace={() => onReplace(c)} />
        </li>
      ))}
      {canManage && onAdd ? (
        <li className="flex">
          <button
            type="button"
            onClick={onAdd}
            className="flex min-h-56 w-full flex-col items-center justify-center gap-3 rounded-[22px] border-2 border-dashed border-line-strong text-muted transition-colors duration-150 hover:border-accent hover:text-accent"
          >
            <span className="grid size-10 place-items-center rounded-full bg-subtle">
              <Plus className="size-5" aria-hidden />
            </span>
            <span className="text-[15px] font-medium">Add certificate</span>
          </button>
        </li>
      ) : null}
    </ul>
  );
}

export function CertificateTable({ certificates, canManage }: { certificates: Certificate[]; canManage: boolean }) {
  const [replacing, setReplacing] = useState<string | null>(null);
  const { verify, remove, open } = useCertificateActions();

  if (!certificates.length) return <p className="text-xs text-muted">No certificates yet.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-left text-sm">
        <caption className="sr-only">Company certificates</caption>
        <thead className="border-b border-line text-xs text-muted">
          <tr>
            <th scope="col" className="py-2.5 pr-3 font-medium">Certificate</th>
            <th scope="col" className="px-3 py-2.5 font-medium">Status</th>
            <th scope="col" className="px-3 py-2.5 font-medium">File</th>
            <th scope="col" className="py-2.5 pl-3 text-right font-medium">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {certificates.map((c) => (
            <Fragment key={c.id}>
              <tr className="border-b border-line align-top last:border-0">
                <td className="py-3 pr-3">
                  <p className="font-medium leading-snug">{c.title}</p>
                  <p className="mt-0.5 text-2xs text-muted">
                    {c.type_label}
                    {c.number ? ` · ${c.number}` : ""}
                    {c.registration_class ? ` · Class ${c.registration_class}` : ""}
                    {c.value_paise ? ` · ${formatINR(c.value_paise)}` : ""}
                  </p>
                </td>
                <td className="px-3 py-3">
                  <div className="flex flex-wrap items-center gap-1">
                    {c.verification_status === "verified" ? (
                      <Chip tone="ok">
                        <ShieldCheck aria-hidden /> Verified
                      </Chip>
                    ) : c.verification_status === "rejected" ? (
                      <Chip tone="danger">Rejected</Chip>
                    ) : (
                      <Chip tone="warn">Unverified</Chip>
                    )}
                    {c.expiry_state !== "none" && c.expiry_state !== "valid" ? (
                      <Chip tone={EXPIRY_CHIP[c.expiry_state].tone}>
                        <AlertTriangle aria-hidden />
                        {EXPIRY_CHIP[c.expiry_state].label}
                      </Chip>
                    ) : null}
                  </div>
                  <p className="tabular mt-1 whitespace-nowrap text-2xs text-muted">{c.expires_on ? `Expires ${formatDateIST(c.expires_on)}` : "No expiry"}</p>
                </td>
                <td className="px-3 py-3 text-xs">
                  {c.document ? (
                    <button type="button" onClick={() => void open(c.document!.id)} className="inline-flex max-w-52 items-center gap-1.5 text-ink hover:text-accent" title={c.document.filename}>
                      <Download className="size-3.5 shrink-0 text-faint" aria-hidden />
                      <span className="truncate">{c.document.filename}</span>
                    </button>
                  ) : (
                    <span className="text-danger">No file</span>
                  )}
                  {c.document ? <p className="pl-5 text-2xs text-muted">{formatBytes(c.document.size_bytes)}</p> : null}
                </td>
                <td className="py-2.5 pl-3">
                  {canManage ? (
                    <div className="flex items-center justify-end gap-0.5 whitespace-nowrap">
                      {c.verification_status !== "verified" && c.document ? (
                        <Button size="sm" onClick={() => verify.mutate({ id: c.id, status: "verified" })} title="Confirm you checked the original against the issuing authority">
                          Mark verified
                        </Button>
                      ) : null}
                      {c.verification_status === "verified" ? (
                        <Button size="sm" variant="quiet" onClick={() => verify.mutate({ id: c.id, status: "unverified" })}>
                          Unverify
                        </Button>
                      ) : null}
                      <Button
                        size="icon"
                        variant="quiet"
                        aria-label={`${c.document ? "Replace file for" : "Upload file for"} ${c.title}`}
                        title={c.document ? "Replace file" : "Upload file"}
                        onClick={() => setReplacing(replacing === c.id ? null : c.id)}
                      >
                        <Upload />
                      </Button>
                      <Button size="icon" variant="quiet" aria-label={`Delete ${c.title}`} title="Delete" onClick={() => remove.mutate(c.id)}>
                        <Trash2 />
                      </Button>
                    </div>
                  ) : null}
                </td>
              </tr>
              {replacing === c.id ? (
                <tr className="border-b border-line bg-subtle/40">
                  <td colSpan={4} className="p-4">
                    <CertificateForm existing={c} onDone={() => setReplacing(null)} />
                  </td>
                </tr>
              ) : null}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
