"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/display";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Checkbox, Switch } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { formatDateIST, formatINR, fromPaise, toPaise, type MoneyUnit } from "@/lib/format";
import { useReference, useSaveProfile } from "@/lib/hooks";
import type { Profile } from "@/lib/types";

export const GSTIN_RE = /^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;
export const PAN_RE = /^[A-Z]{5}\d{4}[A-Z]$/;
export const PHONE_RE = /^(\+91)?[6-9]\d{9}$/;

const optional = (re: RegExp, msg: string) =>
  z
    .string()
    .trim()
    .transform((v) => v.toUpperCase())
    .refine((v) => v === "" || re.test(v), msg);

const BUSINESS_LABEL: Record<string, string> = {
  proprietorship: "Proprietorship",
  partnership: "Partnership firm",
  llp: "LLP",
  private_limited: "Private limited company",
  public_limited: "Public limited company",
  other: "Other",
};

interface StepProps {
  profile: Profile;
  submitLabel: string;
  step?: number;
  onSaved?: () => void;
  secondary?: React.ReactNode;
  readOnly?: boolean;
}

function applyServerErrors(e: unknown, setError: (name: never, err: { message: string }) => void) {
  if (e instanceof ApiError) {
    for (const [k, msg] of Object.entries(e.fieldErrors)) setError(k as never, { message: msg });
    toast.error(e.message);
  } else toast.error("Could not save");
}

function FormFooter({ submitLabel, pending, secondary, readOnly }: { submitLabel: string; pending: boolean; secondary?: React.ReactNode; readOnly?: boolean }) {
  if (readOnly) return <p className="mt-4 text-2xs text-muted">Only owners and admins can edit company details.</p>;
  return (
    <div className="mt-5 flex flex-wrap items-center justify-end gap-2 border-t border-line pt-4">
      {secondary}
      <Button type="submit" variant="primary" disabled={pending}>
        {pending ? "Saving…" : submitLabel}
      </Button>
    </div>
  );
}

/* ---------------------------------------------------------------- Step 1 */

const businessSchema = z.object({
  legal_name: z.string().trim().min(2, "Enter the registered legal name"),
  business_type: z.string().min(1, "Select a business type"),
  gstin: optional(GSTIN_RE, "GSTIN must be 15 characters, e.g. 23ABCDE1234F1Z5"),
  pan: optional(PAN_RE, "PAN must look like ABCDE1234F"),
  contact_name: z.string().trim().max(120),
  contact_email: z.union([z.literal(""), z.email("Enter a valid email")]),
  contact_phone: z.string().trim().refine((v) => v === "" || PHONE_RE.test(v.replace(/[\s-]/g, "")), "Enter a 10-digit Indian mobile number"),
  address: z.string().trim().max(500),
  base_district: z.string(),
});

export function BusinessForm({ profile, submitLabel, step, onSaved, secondary, readOnly }: StepProps) {
  const ref = useReference();
  const save = useSaveProfile();
  const form = useForm<z.input<typeof businessSchema>, unknown, z.output<typeof businessSchema>>({
    resolver: zodResolver(businessSchema),
    defaultValues: {
      legal_name: profile.legal_name,
      business_type: profile.business_type ?? "",
      gstin: profile.gstin ?? "",
      pan: profile.pan ?? "",
      contact_name: profile.contact_name ?? "",
      contact_email: profile.contact_email ?? "",
      contact_phone: profile.contact_phone ?? "",
      address: profile.address ?? "",
      base_district: profile.base_district ?? "",
    },
  });
  const e = form.formState.errors;
  const onSubmit = form.handleSubmit(async (v) => {
    try {
      await save.mutateAsync({
        ...v,
        gstin: v.gstin || null,
        pan: v.pan || null,
        contact_email: v.contact_email || null,
        contact_phone: v.contact_phone || null,
        base_district: v.base_district || null,
        ...(step ? { step } : {}),
      });
      toast.success("Business information saved");
      onSaved?.();
    } catch (err) {
      applyServerErrors(err, form.setError as never);
    }
  });
  return (
    <form onSubmit={onSubmit} noValidate>
      <fieldset disabled={readOnly} className="grid gap-4 md:grid-cols-2">
        <Field label="Company legal name" htmlFor="legal_name" error={e.legal_name?.message} required className="md:col-span-2">
          <Input id="legal_name" {...form.register("legal_name")} />
        </Field>
        <Field label="Business type" htmlFor="business_type" error={e.business_type?.message} required>
          {/* Remount once options load: RHF only writes the saved value into the DOM on registration. */}
          <Select key={ref.data ? "ready" : "loading"} id="business_type" {...form.register("business_type")}>
            <option value="">Select…</option>
            {ref.data?.business_types.map((b) => (
              <option key={b} value={b}>
                {BUSINESS_LABEL[b] ?? b}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Base district" htmlFor="base_district" hint="Used as the centre for your operating radius.">
          <Select key={ref.data ? "ready" : "loading"} id="base_district" {...form.register("base_district")}>
            <option value="">Select…</option>
            {ref.data?.districts.map((d) => (
              <option key={d}>{d}</option>
            ))}
          </Select>
        </Field>
        <Field label="GSTIN" htmlFor="gstin" error={e.gstin?.message} hint="Verify on services.gst.gov.in – TenderOS does not verify automatically.">
          <Input id="gstin" className="font-mono uppercase" maxLength={15} {...form.register("gstin")} />
        </Field>
        <Field label="PAN" htmlFor="pan" error={e.pan?.message}>
          <Input id="pan" className="font-mono uppercase" maxLength={10} {...form.register("pan")} />
        </Field>
        <Field label="Contact person" htmlFor="contact_name" error={e.contact_name?.message}>
          <Input id="contact_name" autoComplete="name" {...form.register("contact_name")} />
        </Field>
        <Field label="Contact email" htmlFor="contact_email" error={e.contact_email?.message}>
          <Input id="contact_email" type="email" autoComplete="email" {...form.register("contact_email")} />
        </Field>
        <Field label="Contact mobile" htmlFor="contact_phone" error={e.contact_phone?.message}>
          <Input id="contact_phone" type="tel" inputMode="tel" autoComplete="tel" placeholder="98XXXXXXXX" {...form.register("contact_phone")} />
        </Field>
        <Field label="Registered address" htmlFor="address" error={e.address?.message} className="md:col-span-2">
          <Textarea id="address" rows={2} {...form.register("address")} />
        </Field>
      </fieldset>
      <FormFooter submitLabel={submitLabel} pending={save.isPending} secondary={secondary} readOnly={readOnly} />
    </form>
  );
}

/* ---------------------------------------------------------------- Step 2 */

export function WorkCategoriesForm({ profile, submitLabel, step, onSaved, secondary, readOnly }: StepProps) {
  const ref = useReference();
  const save = useSaveProfile();
  const [cats, setCats] = useState<string[]>(profile.category_codes);
  const [subs, setSubs] = useState<string[]>(profile.subcategory_codes);
  const [specialties, setSpecialties] = useState(profile.specialties.join(", "));
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (cats.length === 0) {
      setError("Select at least one work category");
      return;
    }
    setError(null);
    try {
      await save.mutateAsync({
        category_codes: cats,
        subcategory_codes: subs.filter((s) => ref.data?.categories.some((c) => cats.includes(c.code) && c.subcategories.some((x) => x.code === s))),
        specialties: specialties.split(",").map((s) => s.trim()).filter(Boolean),
        ...(step ? { step } : {}),
      });
      toast.success("Work categories saved");
      onSaved?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save");
    }
  }
  const toggle = (list: string[], set: (v: string[]) => void, v: string) => set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  return (
    <form onSubmit={submit} noValidate>
      <fieldset disabled={readOnly}>
        <legend className="mb-3 text-xs text-muted">
          <span className="sr-only">Work categories (required). </span>
          Pick every category you bid for. Subcategories sharpen matching.
        </legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {ref.data?.categories.map((c) => {
            const checked = cats.includes(c.code);
            return (
              <div key={c.code} className={`rounded-md border px-3 py-2.5 transition-colors duration-150 ${checked ? "border-accent/40 bg-accent-soft/40" : "border-line"}`}>
                <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
                  <Checkbox checked={checked} onCheckedChange={() => toggle(cats, setCats, c.code)} aria-label={c.name} />
                  {c.name}
                  <span className="text-2xs font-normal text-muted" lang="hi">
                    {c.name_hi}
                  </span>
                </label>
                {checked && c.subcategories.length ? (
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5 pl-6">
                    {c.subcategories.map((s) => (
                      <label key={s.code} className="flex cursor-pointer items-center gap-1.5 text-xs text-muted">
                        <Checkbox checked={subs.includes(s.code)} onCheckedChange={() => toggle(subs, setSubs, s.code)} aria-label={s.name} />
                        {s.name}
                      </label>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
        {error ? (
          <p role="alert" className="mt-2 text-2xs font-medium text-danger">
            {error}
          </p>
        ) : null}
        <Field label="Preferred specialties" htmlFor="specialties" hint="Comma separated, e.g. bituminous, PMGSY, well foundation. Matched against tender titles." className="mt-4">
          <Input id="specialties" value={specialties} onChange={(e) => setSpecialties(e.target.value)} />
        </Field>
      </fieldset>
      <FormFooter submitLabel={submitLabel} pending={save.isPending} secondary={secondary} readOnly={readOnly} />
    </form>
  );
}

/* ---------------------------------------------------------------- Step 3 */

export function MoneyInput({
  id,
  value,
  unit,
  onValue,
  onUnit,
}: {
  id: string;
  value: string;
  unit: MoneyUnit;
  onValue: (v: string) => void;
  onUnit: (u: MoneyUnit) => void;
}) {
  return (
    <div className="flex">
      <span className="inline-flex items-center rounded-l-xl border border-r-0 border-line bg-subtle px-2.5 text-xs text-muted">₹</span>
      <Input id={id} inputMode="decimal" value={value} onChange={(e) => onValue(e.target.value)} className="rounded-none" />
      <select
        aria-label="Unit"
        value={unit}
        onChange={(e) => onUnit(e.target.value as MoneyUnit)}
        className="select-chevron rounded-r-xl border border-l-0 border-line bg-subtle pl-2.5 pr-7 text-xs"
      >
        <option value="lakh">lakh</option>
        <option value="crore">crore</option>
      </select>
    </div>
  );
}

function parseMoney(v: string, unit: MoneyUnit): number | null | "invalid" {
  if (v.trim() === "") return null;
  const n = Number(v.replace(/,/g, ""));
  return Number.isFinite(n) && n >= 0 ? toPaise(n, unit) : "invalid";
}

export function GeographyForm({ profile, submitLabel, step, onSaved, secondary, readOnly }: StepProps) {
  const ref = useReference();
  const save = useSaveProfile();
  const [districts, setDistricts] = useState<string[]>(profile.districts);
  const [filter, setFilter] = useState("");
  const [radius, setRadius] = useState(profile.operating_radius_km?.toString() ?? "");
  const [statewide, setStatewide] = useState(profile.statewide);
  const [minUnit, setMinUnit] = useState<MoneyUnit>("lakh");
  const [maxUnit, setMaxUnit] = useState<MoneyUnit>("crore");
  const [min, setMin] = useState(fromPaise(profile.min_tender_value_paise, "lakh")?.toString() ?? "");
  const [max, setMax] = useState(fromPaise(profile.max_tender_value_paise, "crore")?.toString() ?? "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const visible = useMemo(() => (ref.data?.districts ?? []).filter((d) => d.toLowerCase().includes(filter.toLowerCase())), [ref.data, filter]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const minP = parseMoney(min, minUnit);
    const maxP = parseMoney(max, maxUnit);
    const r = radius.trim() === "" ? null : Number(radius);
    const errs: Record<string, string> = {};
    if (minP === "invalid") errs.min = "Enter a number";
    if (maxP === "invalid") errs.max = "Enter a number";
    if (typeof minP === "number" && typeof maxP === "number" && minP > maxP) errs.max = "Maximum must be at least the minimum";
    if (r !== null && (!Number.isInteger(r) || r < 0 || r > 1000)) errs.radius = "Enter 0–1000 km";
    if (!districts.length && !statewide) errs.districts = "Choose preferred districts or accept statewide work";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    try {
      await save.mutateAsync({
        districts,
        statewide,
        operating_radius_km: r,
        min_tender_value_paise: minP,
        max_tender_value_paise: maxP,
        ...(step ? { step } : {}),
      });
      toast.success("Geography and project size saved");
      onSaved?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save");
    }
  }

  return (
    <form onSubmit={submit} noValidate>
      <fieldset disabled={readOnly} className="space-y-5">
        <div>
          <div className="mb-2 flex items-center justify-between gap-2">
            <legend className="text-xs font-medium">
              Preferred MP districts <span className="tabular text-muted">({districts.length} selected)</span>
            </legend>
            <input
              aria-label="Find district"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Find district"
              className="h-7 w-40 rounded border border-line px-2 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
            />
          </div>
          <div className="grid max-h-56 grid-cols-2 gap-x-3 gap-y-1 overflow-y-auto rounded-md border border-line p-2 sm:grid-cols-3 lg:grid-cols-4">
            {visible.map((d) => (
              <label key={d} className="flex cursor-pointer items-center gap-1.5 rounded px-1 py-0.5 text-xs hover:bg-subtle">
                <Checkbox
                  checked={districts.includes(d)}
                  onCheckedChange={() => setDistricts(districts.includes(d) ? districts.filter((x) => x !== d) : [...districts, d])}
                  aria-label={d}
                />
                {d}
              </label>
            ))}
          </div>
          {errors.districts ? (
            <p role="alert" className="mt-1 text-2xs font-medium text-danger">
              {errors.districts}
            </p>
          ) : null}
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Operating radius (km)" htmlFor="radius" hint="From your base and preferred districts (approximate HQ distances)." error={errors.radius}>
            <Input id="radius" inputMode="numeric" value={radius} onChange={(e) => setRadius(e.target.value)} />
          </Field>
          <Field label="Minimum tender value" htmlFor="min" error={errors.min}>
            <MoneyInput id="min" value={min} unit={minUnit} onValue={setMin} onUnit={setMinUnit} />
          </Field>
          <Field label="Maximum tender value" htmlFor="max" error={errors.max}>
            <MoneyInput id="max" value={max} unit={maxUnit} onValue={setMax} onUnit={setMaxUnit} />
          </Field>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <Switch checked={statewide} onCheckedChange={setStatewide} aria-label="Accept statewide work" />
          Accept work anywhere in Madhya Pradesh (partial location credit outside preferred districts)
        </label>
      </fieldset>
      <FormFooter submitLabel={submitLabel} pending={save.isPending} secondary={secondary} readOnly={readOnly} />
    </form>
  );
}

/* ---------------------------------------------------------------- Step 4 */

export function CapacityForm({ profile, submitLabel, step, onSaved, secondary, readOnly }: StepProps) {
  const ref = useReference();
  const save = useSaveProfile();
  const [v, setV] = useState({
    turnover: fromPaise(profile.annual_turnover_paise, "crore")?.toString() ?? "",
    fy: profile.turnover_financial_year ?? "",
    cls: profile.contractor_registration_class ?? "",
    authority: profile.registration_authority ?? "",
    workforce: profile.workforce_count?.toString() ?? "",
    maxProjects: profile.max_concurrent_projects?.toString() ?? "",
    activeProjects: profile.current_active_projects?.toString() ?? "",
    equipment: profile.equipment.join("\n"),
    resources: profile.available_resources ?? "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const set = (k: keyof typeof v) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setV({ ...v, [k]: e.target.value });
  const int = (s: string) => (s.trim() === "" ? null : Number(s));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    const turnover = parseMoney(v.turnover, "crore");
    if (turnover === "invalid") errs.turnover = "Enter a number in crore";
    if (v.fy && !/^\d{4}-\d{2}$/.test(v.fy)) errs.fy = "Use the format 2025-26";
    for (const k of ["workforce", "maxProjects", "activeProjects"] as const) {
      const n = int(v[k]);
      if (n !== null && (!Number.isInteger(n) || n < 0)) errs[k] = "Enter a whole number";
    }
    const maxP = int(v.maxProjects);
    const act = int(v.activeProjects);
    if (maxP !== null && act !== null && act > maxP) errs.activeProjects = "Cannot exceed maximum concurrent projects";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    try {
      await save.mutateAsync({
        annual_turnover_paise: turnover,
        turnover_financial_year: v.fy || null,
        contractor_registration_class: v.cls || null,
        registration_authority: v.authority || null,
        workforce_count: int(v.workforce),
        max_concurrent_projects: maxP,
        current_active_projects: act,
        equipment: v.equipment.split("\n").map((s) => s.trim()).filter(Boolean),
        available_resources: v.resources || null,
        ...(step ? { step } : {}),
      });
      toast.success("Capacity saved");
      onSaved?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save");
    }
  }

  return (
    <form onSubmit={submit} noValidate>
      <fieldset disabled={readOnly} className="grid gap-4 md:grid-cols-3">
        <Field label="Average annual turnover (₹ crore)" htmlFor="turnover" error={errors.turnover} hint="Upload a CA-certified statement in the document vault for it to count.">
          <Input id="turnover" inputMode="decimal" value={v.turnover} onChange={set("turnover")} />
        </Field>
        <Field label="Latest financial year" htmlFor="fy" error={errors.fy}>
          <Input id="fy" placeholder="2025-26" value={v.fy} onChange={set("fy")} />
        </Field>
        <Field label="Contractor registration class" htmlFor="cls">
          <Select id="cls" value={v.cls} onChange={set("cls")}>
            <option value="">Not registered / unknown</option>
            {ref.data?.registration_classes.map((c) => (
              <option key={c} value={c}>
                Class {c}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Registration authority" htmlFor="authority" className="md:col-span-2">
          <Input id="authority" placeholder="e.g. MP PWD centralised registration" value={v.authority} onChange={set("authority")} />
        </Field>
        <Field label="Workforce (people)" htmlFor="workforce" error={errors.workforce}>
          <Input id="workforce" inputMode="numeric" value={v.workforce} onChange={set("workforce")} />
        </Field>
        <Field label="Max concurrent projects" htmlFor="maxProjects" error={errors.maxProjects}>
          <Input id="maxProjects" inputMode="numeric" value={v.maxProjects} onChange={set("maxProjects")} />
        </Field>
        <Field label="Projects in hand now" htmlFor="activeProjects" error={errors.activeProjects}>
          <Input id="activeProjects" inputMode="numeric" value={v.activeProjects} onChange={set("activeProjects")} />
        </Field>
        <div className="hidden md:block" />
        <Field label="Equipment (one per line)" htmlFor="equipment" hint="Matched against tender equipment criteria. Self-declared." className="md:col-span-2">
          <Textarea id="equipment" rows={4} value={v.equipment} onChange={set("equipment")} />
        </Field>
        <Field label="Other resources" htmlFor="resources">
          <Textarea id="resources" rows={4} value={v.resources} onChange={set("resources")} />
        </Field>
      </fieldset>
      <FormFooter submitLabel={submitLabel} pending={save.isPending} secondary={secondary} readOnly={readOnly} />
    </form>
  );
}

/* ---------------------------------------------------------------- Experience */

export function ExperienceManager({ profile, readOnly }: { profile: Profile; readOnly?: boolean }) {
  const ref = useReference();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ project_name: "", client_name: "", category_code: profile.category_codes[0] ?? "roads", district: "", value: "", completed_on: "", certificate_id: "" });
  const [error, setError] = useState<string | null>(null);
  const certs = profile.certificates.filter((c) => c.cert_type === "experience");
  const refresh = (p: Profile) => {
    qc.setQueryData(["profile"], p);
    void qc.invalidateQueries({ queryKey: ["tenders"] });
  };
  const add = useMutation({
    mutationFn: () =>
      api<Profile>("/api/v1/company/experience", {
        method: "POST",
        json: {
          project_name: f.project_name,
          client_name: f.client_name || null,
          category_code: f.category_code,
          district: f.district || null,
          contract_value_paise: toPaise(Number(f.value), "crore"),
          completed_on: f.completed_on || null,
          certificate_id: f.certificate_id || null,
        },
      }),
    onSuccess: (p) => {
      refresh(p);
      setOpen(false);
      setF({ ...f, project_name: "", client_name: "", value: "", completed_on: "", certificate_id: "" });
      toast.success("Project added");
    },
    onError: (e: Error) => setError(e.message),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api<Profile>(`/api/v1/company/experience/${id}`, { method: "DELETE" }),
    onSuccess: refresh,
  });

  return (
    <div>
      {profile.experience.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <caption className="sr-only">Similar completed projects</caption>
            <thead className="border-b border-line text-xs text-muted">
              <tr>
                <th scope="col" className="py-2 pr-3 font-medium">Project</th>
                <th scope="col" className="px-3 py-2 font-medium">Category</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">Value</th>
                <th scope="col" className="px-3 py-2 font-medium">Completed</th>
                <th scope="col" className="px-3 py-2 font-medium">Certificate</th>
                <th scope="col" className="w-8" />
              </tr>
            </thead>
            <tbody>
              {profile.experience.map((x) => (
                <tr key={x.id} className="border-b border-line last:border-0">
                  <td className="py-2 pr-3">
                    <p>{x.project_name}</p>
                    <p className="text-2xs text-muted">
                      {x.client_name}
                      {x.district ? ` · ${x.district}` : ""}
                    </p>
                  </td>
                  <td className="px-3 py-2 text-xs">{ref.data?.categories.find((c) => c.code === x.category_code)?.name ?? x.category_code}</td>
                  <td className="tabular px-3 py-2 text-right">{formatINR(x.contract_value_paise)}</td>
                  <td className="px-3 py-2 text-xs">{formatDateIST(x.completed_on)}</td>
                  <td className="px-3 py-2">
                    {x.certificate_status === "verified" ? (
                      <Chip tone="ok">Verified</Chip>
                    ) : x.certificate_status ? (
                      <Chip tone="warn">Unverified</Chip>
                    ) : (
                      <Chip tone="danger">Missing</Chip>
                    )}
                  </td>
                  <td>
                    {!readOnly ? (
                      <button type="button" aria-label={`Remove ${x.project_name}`} onClick={() => remove.mutate(x.id)} className="rounded p-1 text-faint hover:text-danger">
                        <Trash2 className="size-3.5" />
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-xs text-muted">No completed projects recorded. Similar-work criteria will show “Needs verification”.</p>
      )}
      {!readOnly ? (
        open ? (
          <form
            className="mt-4 grid gap-3 rounded-md border border-line bg-subtle/40 p-3 md:grid-cols-3"
            onSubmit={(e) => {
              e.preventDefault();
              setError(null);
              if (f.project_name.trim().length < 3 || !(Number(f.value) > 0)) {
                setError("Enter a project name and a contract value greater than zero");
                return;
              }
              add.mutate();
            }}
          >
            <Field label="Project name" htmlFor="exp-name" required className="md:col-span-2">
              <Input id="exp-name" value={f.project_name} onChange={(e) => setF({ ...f, project_name: e.target.value })} />
            </Field>
            <Field label="Client / department" htmlFor="exp-client">
              <Input id="exp-client" value={f.client_name} onChange={(e) => setF({ ...f, client_name: e.target.value })} />
            </Field>
            <Field label="Category" htmlFor="exp-cat" required>
              <Select id="exp-cat" value={f.category_code} onChange={(e) => setF({ ...f, category_code: e.target.value })}>
                {ref.data?.categories.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Contract value (₹ crore)" htmlFor="exp-value" required>
              <Input id="exp-value" inputMode="decimal" value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} />
            </Field>
            <Field label="Completed on" htmlFor="exp-date">
              <Input id="exp-date" type="date" value={f.completed_on} onChange={(e) => setF({ ...f, completed_on: e.target.value })} />
            </Field>
            <Field label="District" htmlFor="exp-district">
              <Select id="exp-district" value={f.district} onChange={(e) => setF({ ...f, district: e.target.value })}>
                <option value="">—</option>
                {ref.data?.districts.map((d) => (
                  <option key={d}>{d}</option>
                ))}
              </Select>
            </Field>
            <Field label="Completion certificate" htmlFor="exp-cert" hint="Upload under Document vault → Experience." className="md:col-span-2">
              <Select id="exp-cert" value={f.certificate_id} onChange={(e) => setF({ ...f, certificate_id: e.target.value })}>
                <option value="">None yet</option>
                {certs.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title} ({c.verification_status})
                  </option>
                ))}
              </Select>
            </Field>
            {error ? (
              <p role="alert" className="text-2xs font-medium text-danger md:col-span-3">
                {error}
              </p>
            ) : null}
            <div className="flex justify-end gap-2 md:col-span-3">
              <Button variant="quiet" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" disabled={add.isPending}>
                Add project
              </Button>
            </div>
          </form>
        ) : (
          <Button className="mt-3" size="sm" onClick={() => setOpen(true)}>
            <Plus /> Add completed project
          </Button>
        )
      ) : null}
    </div>
  );
}
