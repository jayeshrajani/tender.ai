"use client";

/**
 * @author: @dorianbaffier
 * @description: Uptime Card
 * @version: 1.0.0
 * @date: 2026-10-15
 * @license: MIT
 * @website: https://kokonutui.com
 * @github: https://github.com/kokonut-labs/kokonutui
 */

import { CircleCheck, TriangleAlert, X } from "lucide-react";
import {
  type KeyboardEvent,
  type PointerEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { cn } from "@/lib/utils";

// How much wider the bar under the pointer gets, and how far the swell
// spreads, in bars.
const MAGNIFY = 5;
const SPREAD = 2.4;
// Bars ease toward their width at this rate, per second.
const EASE = 18;
const DAY = 86_400_000;

export type DayStatus = "up" | "degraded" | "down" | "skipped" | "none";

export interface IncidentUpdate {
  /** HH:MM, local to the status page. */
  time: string;
  label: string;
  note?: string;
}

export interface Incident {
  title: string;
  status: Exclude<DayStatus, "up" | "none" | "skipped">;
  /** Minutes of impact that day. */
  minutes: number;
  updates: IncidentUpdate[];
}

export interface UptimeService {
  name: string;
  /** Incidents by day index, 0 being the oldest day shown. */
  incidents?: Record<number, Incident>;
  /** Days with no data (before the service existed), from the start. */
  missing?: number;
  /** Explicit status per day, oldest first; overrides incidents for colour. */
  statuses?: DayStatus[];
  /** Shown instead of the uptime percentage. */
  note?: string;
}

export interface UptimeCardProps {
  title?: string;
  services?: UptimeService[];
  days?: number;
  /** The last day shown, as YYYY-MM-DD. */
  endDate?: string;
  /** Headline when nothing is affected today. */
  okLabel?: string;
  className?: string;
}

const DEFAULT_SERVICES: UptimeService[] = [
  {
    name: "API",
    incidents: {
      19: {
        title: "Elevated error rates on writes",
        status: "degraded",
        minutes: 18,
        updates: [
          {
            time: "14:02",
            label: "Investigating",
            note: "5xx on POST rose to 2%.",
          },
          {
            time: "14:11",
            label: "Identified",
            note: "A bad config push to one region.",
          },
          {
            time: "14:20",
            label: "Resolved",
            note: "Rolled back; error rates normal.",
          },
        ],
      },
      84: {
        title: "Slow responses in eu-west",
        status: "degraded",
        minutes: 23,
        updates: [
          {
            time: "09:41",
            label: "Investigating",
            note: "p95 latency up 3x in eu-west.",
          },
          {
            time: "09:52",
            label: "Monitoring",
            note: "Added capacity to the pool.",
          },
          { time: "10:04", label: "Resolved" },
        ],
      },
    },
  },
  {
    name: "Dashboard",
    incidents: {
      43: {
        title: "Charts failed to load",
        status: "degraded",
        minutes: 12,
        updates: [
          { time: "18:30", label: "Investigating" },
          {
            time: "18:42",
            label: "Resolved",
            note: "A CDN cache rule was reverted.",
          },
        ],
      },
    },
  },
  {
    name: "Webhooks",
    incidents: {
      69: {
        title: "Deliveries delayed",
        status: "down",
        minutes: 48,
        updates: [
          {
            time: "02:15",
            label: "Investigating",
            note: "The delivery queue stopped draining.",
          },
          {
            time: "02:38",
            label: "Identified",
            note: "A worker deploy failed health checks.",
          },
          {
            time: "03:03",
            label: "Resolved",
            note: "Backlog delivered in order.",
          },
        ],
      },
    },
  },
  {
    name: "Database",
    missing: 6,
    incidents: {
      27: {
        title: "Failover to replica",
        status: "down",
        minutes: 9,
        updates: [
          {
            time: "22:07",
            label: "Investigating",
            note: "Primary stopped accepting writes.",
          },
          {
            time: "22:16",
            label: "Resolved",
            note: "Promoted the replica; no data lost.",
          },
        ],
      },
    },
  },
];

const clamp = (v: number, lo: number, hi: number) =>
  Math.min(hi, Math.max(lo, v));

const formatDay = (ms: number) =>
  new Date(ms).toLocaleDateString("en-IN", {
    weekday: "short",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });

function statusOf(service: UptimeService, day: number): DayStatus {
  if (service.statuses) {
    return service.statuses[day] ?? "none";
  }
  if (day < (service.missing ?? 0)) {
    return "none";
  }
  return service.incidents?.[day]?.status ?? "up";
}

/** Downtime counts in full, degraded time at half. */
function uptimeOf(service: UptimeService, days: number): number | null {
  if (service.statuses) {
    const ran = service.statuses.filter((s) => s === "up" || s === "degraded" || s === "down");
    if (!ran.length) {
      return null;
    }
    const score = ran.reduce((sum, s) => sum + (s === "up" ? 1 : s === "degraded" ? 0.5 : 0), 0);
    return (100 * score) / ran.length;
  }
  const tracked = days - (service.missing ?? 0);
  let lost = 0;
  for (const incident of Object.values(service.incidents ?? {})) {
    lost += incident.minutes * (incident.status === "down" ? 1 : 0.5);
  }
  return 100 * (1 - lost / (tracked * 1440));
}

/** Target widths: a swell around the focus, flat without one. */
function swell(count: number, focus: number | null, out: Float64Array) {
  for (let i = 0; i < count; i++) {
    out[i] =
      focus === null
        ? 1
        : 1 + MAGNIFY * Math.exp(-(((i - focus) / SPREAD) ** 2));
  }
  return out;
}

/** The bar under x (0 to 1) when bars have these widths. */
function barAt(weights: Float64Array, x: number) {
  let total = 0;
  for (const w of weights) {
    total += w;
  }
  let at = x * total;
  for (let i = 0; i < weights.length; i++) {
    at -= weights[i] ?? 0;
    if (at <= 0) {
      return i;
    }
  }
  return weights.length - 1;
}

function incidentsOn(services: UptimeService[], day: number) {
  return services.flatMap((s) => {
    const incident = s.incidents?.[day];
    return incident ? [{ service: s.name, incident }] : [];
  });
}

function describeDay(list: { service: string; incident: Incident }[]) {
  const first = list[0];
  if (!first) {
    return "No incidents";
  }
  const how = first.incident.status === "down" ? "down" : "degraded";
  const more = list.length > 1 ? `, +${list.length - 1} more` : "";
  if (!first.incident.minutes) {
    return `${first.service}: ${first.incident.title}${more}`;
  }
  return `${first.service} ${how} for ${first.incident.minutes} min${more}`;
}

const BAR_COLOR: Record<DayStatus, string> = {
  up: "bg-ok",
  degraded: "bg-warn",
  down: "bg-danger",
  skipped: "bg-line-strong",
  none: "bg-subtle",
};

const STATUS_TEXT: Record<DayStatus, string> = {
  up: "Operational",
  degraded: "Degraded",
  down: "Outage",
  skipped: "Skipped",
  none: "No data",
};

export default function UptimeCard({
  title = "System status",
  services = DEFAULT_SERVICES,
  days = 90,
  endDate = "2026-10-14",
  okLabel = "All systems operational",
  className,
}: UptimeCardProps) {
  const [active, setActive] = useState<number | null>(null);
  const [pinned, setPinned] = useState<number | null>(null);
  const barsRef = useRef<HTMLDivElement>(null);
  const sim = useRef({
    weights: new Float64Array(days).fill(1),
    target: new Float64Array(days).fill(1),
    focus: null as number | null,
    raf: 0,
    last: 0,
    reduceMotion: false,
  });
  if (sim.current.weights.length !== days) {
    sim.current.weights = new Float64Array(days).fill(1);
    sim.current.target = new Float64Array(days).fill(1);
  }

  const end = Date.parse(`${endDate}T00:00:00Z`);
  const dateOf = useCallback(
    (day: number) => end - (days - 1 - day) * DAY,
    [end, days]
  );
  const uptimes = useMemo(
    () => services.map((s) => uptimeOf(s, days)),
    [services, days]
  );
  const openIssues = services.filter((s) => {
    const today = statusOf(s, days - 1);
    return today === "degraded" || today === "down";
  });

  // Widths are written straight to the bars, one flex-grow per bar.
  const paint = useCallback(() => {
    const rows = barsRef.current?.querySelectorAll<HTMLElement>("[data-row]");
    const { weights } = sim.current;
    for (const row of rows ?? []) {
      const bars = row.children;
      for (let i = 0; i < bars.length; i++) {
        (bars[i] as HTMLElement).style.flexGrow = (weights[i] ?? 1).toFixed(3);
      }
    }
  }, []);

  const tick = useCallback(
    (now: number) => {
      const s = sim.current;
      s.raf = 0;
      const dt = s.last ? Math.min((now - s.last) / 1000, 1 / 30) : 1 / 60;
      s.last = now;
      const k = 1 - Math.exp(-EASE * dt);
      let moving = false;
      for (let i = 0; i < s.weights.length; i++) {
        const target = s.target[i] ?? 1;
        const weight = s.weights[i] ?? 1;
        const gap = target - weight;
        if (Math.abs(gap) > 0.002) {
          s.weights[i] = weight + gap * k;
          moving = true;
        } else {
          s.weights[i] = target;
        }
      }
      paint();
      if (moving) {
        s.raf = requestAnimationFrame(tick);
      } else {
        s.last = 0;
      }
    },
    [paint]
  );

  const focusOn = useCallback(
    (focus: number | null) => {
      const s = sim.current;
      s.focus = focus;
      swell(s.weights.length, focus, s.target);
      if (s.reduceMotion) {
        s.weights.set(s.target);
        paint();
      } else if (!s.raf) {
        s.raf = requestAnimationFrame(tick);
      }
    },
    [paint, tick]
  );

  useEffect(() => {
    const s = sim.current;
    s.reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;
    return () => cancelAnimationFrame(s.raf);
  }, []);

  /** The day under the pointer, found against the swollen layout. */
  const dayAt = (clientX: number) => {
    const rect = barsRef.current?.getBoundingClientRect();
    if (!rect) {
      return 0;
    }
    const x = clamp((clientX - rect.left) / rect.width, 0, 1);
    const probe = new Float64Array(days);
    let day = Math.round(x * (days - 1));
    // Centre the swell on the bar that ends up under the pointer.
    for (let pass = 0; pass < 3; pass++) {
      day = barAt(swell(days, day, probe), x);
    }
    return day;
  };

  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (
      event.pointerType !== "mouse" &&
      !event.currentTarget.hasPointerCapture(event.pointerId)
    ) {
      return;
    }
    const day = dayAt(event.clientX);
    // Most moves stay on the same bar: skip the re-render and the retarget.
    if (day === active) {
      return;
    }
    setActive(day);
    focusOn(day);
  };

  const handlePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.pointerType === "mouse" && event.button !== 0) {
      return;
    }
    if (event.pointerType !== "mouse") {
      event.currentTarget.setPointerCapture(event.pointerId);
    }
    const day = dayAt(event.clientX);
    setActive(day);
    focusOn(day);
  };

  const handleClick = () => {
    if (active !== null) {
      setPinned((p) => (p === active ? null : active));
    }
  };

  const leave = () => {
    setActive(null);
    focusOn(pinned);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const from = active ?? pinned ?? days - 1;
    const moves: Record<string, number> = {
      ArrowLeft: -1,
      ArrowRight: 1,
      Home: -days,
      End: days,
    };
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setPinned((p) => (p === from ? null : from));
      return;
    }
    if (event.key === "Escape") {
      setPinned(null);
      setActive(null);
      focusOn(null);
      return;
    }
    const move = moves[event.key];
    if (move === undefined) {
      return;
    }
    event.preventDefault();
    const day = clamp(from + move, 0, days - 1);
    setActive(day);
    focusOn(day);
  };

  const shownDay = active ?? pinned;
  const summary =
    shownDay === null
      ? "Hover a day to see what happened"
      : `${formatDay(dateOf(shownDay))} · ${describeDay(incidentsOn(services, shownDay))}`;
  // The log keeps showing the last pinned day while it collapses.
  const lastPinned = useRef<number | null>(null);
  if (pinned !== null) {
    lastPinned.current = pinned;
  }
  const logDay = pinned ?? lastPinned.current;
  const pinnedIncidents = logDay === null ? [] : incidentsOn(services, logDay);

  return (
    <div
      className={cn(
        "w-full select-none rounded-[22px] bg-surface p-6 text-ink",
        className
      )}
    >
      <div className="flex items-center justify-between gap-4">
        <p className="font-semibold text-[15px]">{title}</p>
        {openIssues.length ? (
          <p className="flex items-center gap-1.5 text-sm text-warn">
            <TriangleAlert aria-hidden className="size-4" />
            {openIssues.length} source{openIssues.length > 1 ? "s" : ""}{" "}
            affected today
          </p>
        ) : (
          <p className="flex items-center gap-1.5 text-sm text-ok">
            <CircleCheck aria-hidden className="size-4" />
            {okLabel}
          </p>
        )}
      </div>
      <p
        aria-live="polite"
        className="mt-1 truncate text-sm text-muted tabular-nums"
      >
        {summary}
      </p>

      <div
        aria-label={`Daily status for the last ${days} days. Use the arrow keys to move between days and Enter to open one.`}
        aria-valuemax={days}
        aria-valuemin={1}
        aria-valuenow={(shownDay ?? days - 1) + 1}
        aria-valuetext={summary}
        className="mt-5 cursor-pointer touch-pan-y rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-4 focus-visible:ring-offset-surface"
        onBlur={() => {
          if (active !== null) {
            leave();
          }
        }}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        onLostPointerCapture={(event) => {
          // A touch's implicit capture on the bar it started on moves to this
          // element on pointerdown; that bubbling event is not the end.
          if (event.target === event.currentTarget) {
            leave();
          }
        }}
        onPointerDown={handlePointerDown}
        onPointerLeave={(event) => {
          if (event.pointerType === "mouse") {
            leave();
          }
        }}
        onPointerMove={handlePointerMove}
        ref={barsRef}
        role="slider"
        tabIndex={0}
      >
        {services.map((service, row) => {
          const uptime = uptimes[row] ?? null;
          return (
          <div className={cn(row > 0 && "mt-4")} key={service.name}>
            <div className="mb-1.5 flex justify-between text-[13px]">
              <span className="font-medium">{service.name}</span>
              <span className="text-muted tabular-nums">
                {service.note ??
                  (uptime === null
                    ? "No runs"
                    : `${uptime.toFixed(uptime === 100 ? 0 : 1)}%`)}
              </span>
            </div>
            <div className="flex h-8 gap-[2px] sm:gap-[3px]" data-row>
              {Array.from({ length: days }, (_, day) => {
                const status = statusOf(service, day);
                const lit = day === shownDay;
                return (
                  <div
                    className={cn(
                      "min-w-0 basis-0 rounded-full transition-opacity duration-150 ease-out",
                      BAR_COLOR[status],
                      shownDay !== null && !lit && "opacity-60"
                    )}
                    // biome-ignore lint/suspicious/noArrayIndexKey: one bar per day, never reordered
                    key={day}
                    style={{ flexGrow: 1 }}
                  />
                );
              })}
            </div>
          </div>
          );
        })}
        <div className="mt-3 flex justify-between text-xs text-faint">
          <span>{days} days ago</span>
          <span>Today</span>
        </div>
      </div>

      {/* A pinned day opens its incident log. */}
      <div
        className={cn(
          "grid transition-[grid-template-rows,opacity] duration-[260ms] ease-[cubic-bezier(0.23,1,0.32,1)]",
          pinned === null
            ? "grid-rows-[0fr] opacity-0"
            : "grid-rows-[1fr] opacity-100"
        )}
        inert={pinned === null}
      >
        <div className="overflow-hidden">
          {logDay !== null && (
            <div className="mt-4 rounded-2xl bg-subtle p-4">
              <div className="flex items-center justify-between">
                <p className="font-medium text-sm">
                  {formatDay(dateOf(logDay))}
                </p>
                <button
                  aria-label="Close day"
                  className="rounded-full p-1 text-muted outline-none transition-colors duration-150 ease-out hover:bg-line hover:text-ink focus-visible:ring-2 focus-visible:ring-accent"
                  onClick={() => {
                    setPinned(null);
                    focusOn(null);
                  }}
                  type="button"
                >
                  <X aria-hidden className="size-3.5" />
                </button>
              </div>
              {pinnedIncidents.length === 0 && (
                <p className="mt-1 text-sm text-muted">
                  No failed or partial runs that day.
                </p>
              )}
              {pinnedIncidents.map(({ service, incident }) => (
                <div className="mt-3" key={service}>
                  <p className="flex flex-wrap items-center gap-2 text-sm">
                    <span
                      className={cn(
                        "size-2 rounded-full",
                        incident.status === "down" ? "bg-danger" : "bg-warn"
                      )}
                    />
                    <span className="font-medium">{service}</span>
                    <span className="text-muted">
                      {STATUS_TEXT[incident.status]} · {incident.title}
                      {incident.minutes ? ` · ${incident.minutes} min` : ""}
                    </span>
                  </p>
                  {incident.updates.length > 0 && (
                  <ol className="mt-2.5 ml-1 border-line border-l">
                    {incident.updates.map((update) => (
                      <li
                        className="relative pb-2.5 pl-4 text-sm last:pb-0"
                        key={`${update.time}-${update.label}`}
                      >
                        <span className="absolute top-[7px] -left-[3.5px] size-1.5 rounded-full bg-faint" />
                        <span className="text-faint tabular-nums">
                          {update.time}
                        </span>{" "}
                        <span className="font-medium">{update.label}</span>
                        {update.note && (
                          <span className="text-muted">
                            {" "}
                            {update.note}
                          </span>
                        )}
                      </li>
                    ))}
                  </ol>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
