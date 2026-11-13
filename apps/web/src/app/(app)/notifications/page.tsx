"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Send } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { NotificationPrefsForm } from "@/components/notifications/prefs-form";
import { Button } from "@/components/ui/button";
import { Chip, EmptyState, ErrorState, PageHeader, Panel, Skeleton } from "@/components/ui/display";
import { api, qs } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDateTimeIST, titleCase } from "@/lib/format";
import { canEdit, useMe } from "@/lib/hooks";
import type { NotificationPrefs, OutboxItem } from "@/lib/types";

const KINDS = [
  { value: "closing_48h", label: "48-hour reminder" },
  { value: "deadline_change", label: "Deadline change" },
  { value: "daily_digest", label: "Daily digest" },
];

const STATUS_TONE: Record<string, "accent" | "ok" | "warn" | "danger" | "muted" | "outline"> = {
  simulated: "outline",
  sent: "ok",
  delivered: "ok",
  read: "ok",
  pending: "muted",
  retry: "warn",
  held_quiet_hours: "warn",
  skipped_opt_out: "muted",
  failed: "danger",
};

function Preview() {
  const [kind, setKind] = useState("closing_48h");
  const q = useQuery({
    queryKey: ["notification-preview", kind],
    queryFn: () => api<{ text: string; template: string; tender_id?: string }>(`/api/v1/notifications/preview${qs({ kind })}`),
  });
  return (
    <div>
      <div role="radiogroup" aria-label="Alert type" className="mb-3 inline-flex rounded-md border border-line p-0.5">
        {KINDS.map((k) => (
          <button
            key={k.value}
            role="radio"
            aria-checked={kind === k.value}
            onClick={() => setKind(k.value)}
            className={cn("rounded px-2.5 py-1 text-xs", kind === k.value ? "bg-accent text-on-accent" : "text-muted hover:text-ink")}
          >
            {k.label}
          </button>
        ))}
      </div>
      {q.isLoading ? (
        <Skeleton className="h-56 w-full" />
      ) : q.error ? (
        <p className="text-xs text-muted">{q.error.message}</p>
      ) : (
        <figure>
          <div className="rounded-xl bg-accent-soft/60 p-3">
            <pre className="whitespace-pre-wrap rounded-lg bg-surface p-3 font-sans text-xs leading-relaxed shadow-card">{q.data?.text}</pre>
          </div>
          <figcaption className="mt-1.5 text-2xs text-muted">
            Template <span className="font-mono">{q.data?.template}</span> · rendered exactly as it would be sent; nothing is queued by previewing.
          </figcaption>
        </figure>
      )}
    </div>
  );
}

export default function NotificationsPage() {
  const me = useMe();
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const prefs = useQuery({ queryKey: ["notification-prefs"], queryFn: () => api<NotificationPrefs>("/api/v1/notifications/preferences") });
  const outbox = useQuery({
    queryKey: ["outbox", page],
    queryFn: () => api<{ items: OutboxItem[]; total: number; page_size: number }>(`/api/v1/notifications/outbox${qs({ page })}`),
  });
  const test = useMutation({
    mutationFn: () => api<{ status: string; simulated: boolean; error: string | null }>("/api/v1/notifications/test", { method: "POST" }),
    onSuccess: (r) => {
      if (r.simulated) toast.success("SIMULATED test stored in the outbox. No WhatsApp message was sent.");
      else if (r.status === "sent") toast.success("Test sent via Meta WhatsApp Cloud API.");
      else toast.error(`Test not sent: ${r.error ?? r.status}`);
      void qc.invalidateQueries({ queryKey: ["outbox"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const simulated = prefs.data?.transport === "simulated";

  return (
    <>
      <PageHeader
        title="Notification center"
        description="Get a WhatsApp nudge before a deadline slips. One alert per tender per event, so no spam."
        actions={
          <Button onClick={() => test.mutate()} disabled={test.isPending || !prefs.data?.whatsapp_opt_in || !canEdit(me.data?.active_company?.role, "analyst")}>
            <Send /> {simulated ? "Send simulated test" : "Send test"}
          </Button>
        }
      />
      {prefs.data ? (
        <div
          role="status"
          className={cn(
            "mb-6 flex items-center gap-2.5 rounded-xl border px-4 py-3 text-xs",
            simulated ? "border-line bg-surface text-muted" : "border-accent-line bg-accent-soft text-accent-ink",
          )}
        >
          <span className={cn("size-2 shrink-0 rounded-full", simulated ? "bg-warn" : "bg-accent")} aria-hidden />
          <span>
            <span className="font-semibold text-ink">{simulated ? "Simulated delivery." : "Meta Cloud API connected."}</span>{" "}
            {prefs.data.transport_note.replace(/^SIMULATED:\s*(.)/i, (_, c: string) => c.toUpperCase())}
          </span>
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <Panel title="Your preferences">
          {prefs.error ? <ErrorState message={prefs.error.message} /> : prefs.data ? <NotificationPrefsForm prefs={prefs.data} /> : <Skeleton className="h-72 w-full" />}
        </Panel>
        <Panel title="Message preview" description="Uses your highest-relevance open tender.">
          <Preview />
        </Panel>
      </div>

      <Panel title="Outbox" className="mt-6" bodyClassName="px-0 pb-0" description="Every queued alert with its delivery state. Phone numbers are masked.">
        {outbox.isLoading ? (
          <div className="p-4">
            <Skeleton className="h-40 w-full" />
          </div>
        ) : outbox.data && outbox.data.items.length ? (
          <ul className="divide-y divide-line border-t border-line">
            {outbox.data.items.map((o) => (
              <li key={o.id} className="grid gap-2 px-5 py-3 md:grid-cols-[200px_minmax(0,1fr)_160px]">
                <div className="text-xs">
                  <p className="font-medium">{titleCase(o.alert_type)}</p>
                  <p className="tabular text-2xs text-muted">{formatDateTimeIST(o.created_at)}</p>
                  <p className="text-2xs text-muted">To {o.recipient ?? "—"}</p>
                </div>
                <details className="min-w-0 text-xs">
                  <summary className="cursor-pointer truncate text-ink">{o.rendered_text.split("\n").slice(0, 3).join(" · ")}</summary>
                  <pre className="mt-2 whitespace-pre-wrap rounded-md bg-subtle p-2 font-sans text-2xs leading-relaxed">{o.rendered_text}</pre>
                  {o.tender_id ? (
                    <Link href={`/tenders/${o.tender_id}`} className="mt-1 inline-block text-2xs text-accent hover:underline">
                      Open tender
                    </Link>
                  ) : null}
                </details>
                <div className="flex flex-wrap items-start gap-1 md:justify-end">
                  <Chip tone={STATUS_TONE[o.status] ?? "muted"} className="capitalize">
                    {o.status.replace(/_/g, " ")}
                  </Chip>
                  <Chip tone="muted" className="font-mono">
                    {o.transport}
                  </Chip>
                  {o.error ? <p className="w-full text-right text-2xs text-danger">{o.error}</p> : null}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="Outbox is empty" body="Alerts appear here after the next scheduled run (00:00, 08:00, 16:00 IST) or a test message." />
        )}
        {outbox.data && outbox.data.total > outbox.data.page_size ? (
          <div className="flex justify-end gap-1 border-t border-line px-4 py-2">
            <Button size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Previous
            </Button>
            <Button size="sm" disabled={page * outbox.data.page_size >= outbox.data.total} onClick={() => setPage(page + 1)}>
              Next
            </Button>
          </div>
        ) : null}
      </Panel>
    </>
  );
}
