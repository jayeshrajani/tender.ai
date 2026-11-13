const IST = "Asia/Kolkata";
const CRORE = 10_000_000;
const LAKH = 100_000;

const groupIN = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

/** Compact Indian currency from paise: ₹12.40 Cr, ₹96.00 L, ₹9,500. */
export function formatINR(paise: number | null | undefined): string {
  if (paise === null || paise === undefined) return "Not stated";
  const rupees = paise / 100;
  if (rupees >= CRORE) return `₹${(rupees / CRORE).toFixed(2)} Cr`;
  if (rupees >= LAKH) return `₹${(rupees / LAKH).toFixed(2)} L`;
  return `₹${groupIN.format(rupees)}`;
}

export function formatINRFull(paise: number | null | undefined): string {
  if (paise === null || paise === undefined) return "Not stated";
  return `₹${new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(paise / 100)}`;
}

export type MoneyUnit = "lakh" | "crore";

export function toPaise(value: number, unit: MoneyUnit): number {
  return Math.round(value * (unit === "crore" ? CRORE : LAKH) * 100);
}

export function fromPaise(paise: number | null | undefined, unit: MoneyUnit): number | null {
  if (paise === null || paise === undefined) return null;
  return Math.round((paise / 100 / (unit === "crore" ? CRORE : LAKH)) * 100) / 100;
}

const dateTimeFmt = new Intl.DateTimeFormat("en-IN", {
  timeZone: IST,
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: true,
});
const dateFmt = new Intl.DateTimeFormat("en-IN", { timeZone: IST, day: "2-digit", month: "short", year: "numeric" });
const shortFmt = new Intl.DateTimeFormat("en-IN", { timeZone: IST, day: "2-digit", month: "short" });
const timeFmt = new Intl.DateTimeFormat("en-IN", { timeZone: IST, hour: "2-digit", minute: "2-digit", hour12: true });

export function formatDateTimeIST(iso: string | null | undefined): string {
  if (!iso) return "Not stated";
  return `${dateTimeFmt.format(new Date(iso)).replace(/\s?(am|pm)$/i, (m) => m.toUpperCase())} IST`;
}

export function formatDateIST(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dateFmt.format(new Date(iso));
}

export function formatShortDateIST(iso: string | null | undefined): string {
  if (!iso) return "—";
  return shortFmt.format(new Date(iso));
}

export function formatTimeIST(iso: string | null | undefined): string {
  if (!iso) return "";
  return timeFmt.format(new Date(iso)).toUpperCase();
}

export type DeadlineTone = "closed" | "urgent" | "soon" | "normal" | "unknown";

export function deadlineInfo(iso: string | null | undefined, now: Date = new Date()): { label: string; tone: DeadlineTone } {
  if (!iso) return { label: "Not stated", tone: "unknown" };
  const ms = new Date(iso).getTime() - now.getTime();
  if (ms <= 0) return { label: "Closed", tone: "closed" };
  const hours = ms / 36e5;
  if (hours < 48) return { label: hours < 24 ? `${Math.max(1, Math.round(hours))}h left` : "Tomorrow", tone: "urgent" };
  const days = Math.floor(hours / 24);
  if (days <= 7) return { label: `${days} days left`, tone: "soon" };
  return { label: `${days} days left`, tone: "normal" };
}

export function formatBytes(n: number | null | undefined): string {
  if (!n) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const PERMISSION_LABEL: Record<string, string> = {
  not_required_demo: "Fictional data, no permission needed",
  operator_attested: "Operator-attested",
  pending_authorization: "Awaiting written authorisation",
  authorized: "Authorised",
  link_only: "Link only, not collected",
};

export function permissionLabel(s: string): string {
  return PERMISSION_LABEL[s] ?? titleCase(s);
}
