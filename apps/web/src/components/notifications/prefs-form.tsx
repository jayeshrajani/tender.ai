"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/display";
import { Field, Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { formatDateTimeIST } from "@/lib/format";
import type { NotificationPrefs } from "@/lib/types";

function ToggleRow({ label, hint, checked, onChange }: { label: string; hint: string; checked: boolean; onChange: (b: boolean) => void }) {
  return (
    <label className="flex items-start justify-between gap-4 py-2.5">
      <span>
        <span className="block text-sm">{label}</span>
        <span className="block text-2xs text-muted">{hint}</span>
      </span>
      <Switch checked={checked} onCheckedChange={onChange} aria-label={label} />
    </label>
  );
}

export function NotificationPrefsForm({ prefs, submitLabel = "Save preferences", onSaved }: { prefs: NotificationPrefs; submitLabel?: string; onSaved?: () => void }) {
  const qc = useQueryClient();
  const [v, setV] = useState({
    phone: prefs.phone_e164?.replace(/^\+91/, "") ?? "",
    optIn: prefs.whatsapp_opt_in,
    digest: prefs.daily_digest,
    urgent: prefs.urgent_alerts,
    closing: prefs.closing_reminders,
    minRelevance: String(prefs.min_relevance),
    includeVerify: prefs.include_needs_verification,
    quietStart: prefs.quiet_hours_start ?? "",
    quietEnd: prefs.quiet_hours_end ?? "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: () =>
      api<NotificationPrefs>("/api/v1/notifications/preferences", {
        method: "PUT",
        json: {
          phone_e164: v.phone.trim() ? v.phone.trim() : null,
          whatsapp_opt_in: v.optIn,
          daily_digest: v.digest,
          urgent_alerts: v.urgent,
          closing_reminders: v.closing,
          min_relevance: Number(v.minRelevance),
          include_needs_verification: v.includeVerify,
          quiet_hours_start: v.quietStart || null,
          quiet_hours_end: v.quietEnd || null,
        },
      }),
    onSuccess: (data) => {
      qc.setQueryData(["notification-prefs"], data);
      toast.success("Notification preferences saved");
      onSaved?.();
    },
    onError: (e) => {
      if (e instanceof ApiError) setErrors({ ...e.fieldErrors, form: e.message });
    },
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    const digits = v.phone.replace(/[\s-]/g, "");
    if (digits && !/^[6-9]\d{9}$/.test(digits)) errs.phone_e164 = "Enter a 10-digit Indian mobile number";
    if (v.optIn && !digits) errs.phone_e164 = "A mobile number is required to opt in";
    const mr = Number(v.minRelevance);
    if (!Number.isInteger(mr) || mr < 0 || mr > 100) errs.min_relevance = "0–100";
    if (Boolean(v.quietStart) !== Boolean(v.quietEnd)) errs.quiet = "Set both start and end, or neither";
    setErrors(errs);
    if (!Object.keys(errs).length) save.mutate();
  }

  const Row = ToggleRow;

  return (
    <form onSubmit={submit} noValidate>
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="WhatsApp mobile number" htmlFor="phone" error={errors.phone_e164} hint={prefs.phone_verified ? "Verified" : "Not yet verified by a reply from this number."}>
          <div className="flex">
            <span className="inline-flex items-center rounded-l-md border border-r-0 border-line bg-subtle px-2 text-xs text-muted">+91</span>
            <Input id="phone" type="tel" inputMode="tel" value={v.phone} onChange={(e) => setV({ ...v, phone: e.target.value })} className="rounded-l-none" />
          </div>
        </Field>
        <div className="rounded-md border border-line p-3">
          <label className="flex items-start gap-3">
            <Switch checked={v.optIn} onCheckedChange={(b) => setV({ ...v, optIn: b })} aria-label="WhatsApp opt-in" />
            <span className="text-xs">
              <span className="block font-medium text-ink">I agree to receive tender alerts on WhatsApp</span>
              <span className="text-muted">You can reply STOP at any time. Opt-in is recorded with a timestamp.</span>
            </span>
          </label>
          {prefs.opt_in_at && prefs.whatsapp_opt_in ? <p className="mt-1.5 text-2xs text-muted">Opted in {formatDateTimeIST(prefs.opt_in_at)}</p> : null}
          {prefs.opted_out_at ? (
            <Chip tone="warn" className="mt-1.5">
              Opted out {formatDateTimeIST(prefs.opted_out_at)}
            </Chip>
          ) : null}
        </div>
      </div>

      <div className="mt-4 divide-y divide-line border-y border-line">
        <Row label="Daily digest at 09:00 IST" hint="Top matches that are eligible or need verification." checked={v.digest} onChange={(b) => setV({ ...v, digest: b })} />
        <Row label="Deadline changes" hint="High-priority alert when a corrigendum moves a deadline." checked={v.urgent} onChange={(b) => setV({ ...v, urgent: b })} />
        <Row label="48-hour closing reminders" hint="For relevant or saved tenders." checked={v.closing} onChange={(b) => setV({ ...v, closing: b })} />
        <Row
          label="Include “Needs verification” tenders"
          hint="Off = only tenders where all mandatory criteria are met."
          checked={v.includeVerify}
          onChange={(b) => setV({ ...v, includeVerify: b })}
        />
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <Field label="Minimum relevance (0–100)" htmlFor="min-relevance" error={errors.min_relevance}>
          <Input id="min-relevance" inputMode="numeric" value={v.minRelevance} onChange={(e) => setV({ ...v, minRelevance: e.target.value })} />
        </Field>
        <Field label="Quiet hours start (IST)" htmlFor="quiet-start" error={errors.quiet}>
          <Input id="quiet-start" type="time" value={v.quietStart} onChange={(e) => setV({ ...v, quietStart: e.target.value })} />
        </Field>
        <Field label="Quiet hours end (IST)" htmlFor="quiet-end">
          <Input id="quiet-end" type="time" value={v.quietEnd} onChange={(e) => setV({ ...v, quietEnd: e.target.value })} />
        </Field>
      </div>
      {errors.form ? (
        <p role="alert" className="mt-3 text-xs text-danger">
          {errors.form}
        </p>
      ) : null}
      <div className="mt-4 flex justify-end">
        <Button type="submit" variant="primary" disabled={save.isPending}>
          {save.isPending ? "Saving…" : submitLabel}
        </Button>
      </div>
    </form>
  );
}
