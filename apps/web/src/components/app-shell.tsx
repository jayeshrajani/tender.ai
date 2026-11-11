"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  Building2,
  CalendarClock,
  CheckCircle2,
  Database,
  FileCheck2,
  FileUp,
  LayoutList,
  Menu,
  Search,
  ShieldAlert,
  Sparkles,
  SquareStack,
  Star,
  SunMoon,
  UserPlus,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useMemo, useState } from "react";

import ActionSearchBar, { type CommandItem } from "@/components/kokonutui/action-search-bar";
import ProfileDropdown from "@/components/kokonutui/profile-dropdown";
import SwitchButton from "@/components/kokonutui/switch-button";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { titleCase } from "@/lib/format";
import { useLogout, useMe } from "@/lib/hooks";
import type { Me, TenderList } from "@/lib/types";

const NAV: { group: string; items: { href: string; label: string; icon: typeof Bell; match?: (p: string, s: URLSearchParams) => boolean }[] }[] = [
  {
    group: "Work",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutList },
      { href: "/tenders", label: "Tender explorer", icon: SquareStack, match: (p, s) => p.startsWith("/tenders") && s.get("saved") !== "true" },
      { href: "/tenders?saved=true", label: "Saved tenders", icon: Star, match: (p, s) => p === "/tenders" && s.get("saved") === "true" },
    ],
  },
  {
    group: "Company",
    items: [
      { href: "/company", label: "Company profile", icon: Building2, match: (p) => p === "/company" || p === "/onboarding" },
      { href: "/company/documents", label: "Document vault", icon: FileCheck2 },
    ],
  },
  {
    group: "Operations",
    items: [
      { href: "/notifications", label: "Notifications", icon: Bell },
      { href: "/sources", label: "Data sources", icon: Database },
      { href: "/settings/team", label: "Team", icon: Users },
    ],
  },
];

export function Sidebar({ me, onNavigate }: { me: Me; onNavigate?: () => void }) {
  const pathname = usePathname();
  const search = useSearchParams();

  return (
    <nav aria-label="Main" className="flex h-full flex-col">
      <div className="flex h-16 items-center gap-2.5 px-5">
        <span className="grid size-8 rotate-[-6deg] place-items-center rounded-xl bg-gradient-to-br from-accent to-[#8b5cf6] font-display text-sm font-bold text-white shadow-[0_6px_16px_-6px_var(--accent)]">
          T
        </span>
        <span className="font-display text-lg font-semibold tracking-[-0.02em]">TenderOS</span>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto px-3 pt-2">
        {NAV.map((g) => (
          <div key={g.group}>
            <p className="px-2.5 pb-1.5 text-2xs font-medium text-faint">{g.group}</p>
            <ul className="space-y-0.5">
              {g.items.map((item) => {
                const active = item.match ? item.match(pathname, search) : pathname === item.href;
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "flex h-9 items-center gap-3 rounded-xl px-2.5 text-[13px] transition-colors duration-150",
                        active ? "bg-accent-soft font-medium text-accent-ink" : "text-muted hover:bg-subtle hover:text-ink",
                      )}
                    >
                      <Icon className={cn("size-4", active ? "text-accent" : "text-faint")} aria-hidden />
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      {me.active_company?.is_demo ? (
        <div className="m-3 rounded-2xl bg-gradient-to-br from-accent-soft to-subtle p-3 text-2xs leading-relaxed text-muted">
          <p className="mb-0.5 flex items-center gap-1.5 font-semibold text-accent-ink">
            <Sparkles className="size-3.5" aria-hidden /> Demo playground
          </p>
          Fictional tenders to explore freely. Nothing here is live government data.
        </div>
      ) : null}
    </nav>
  );
}

const ICON = "size-4";

const PAGES: (CommandItem & { path: string })[] = [
  { id: "go-dashboard", label: "Dashboard", path: "/dashboard", icon: <LayoutList className={ICON} />, group: "Go to" },
  { id: "go-tenders", label: "Tender explorer", path: "/tenders", icon: <SquareStack className={ICON} />, group: "Go to", keywords: ["search", "list"] },
  { id: "go-saved", label: "Saved tenders", path: "/tenders?saved=true", icon: <Star className={ICON} />, group: "Go to" },
  { id: "go-company", label: "Company profile", path: "/company", icon: <Building2 className={ICON} />, group: "Go to", keywords: ["turnover", "districts"] },
  { id: "go-documents", label: "Document vault", path: "/company/documents", icon: <FileCheck2 className={ICON} />, group: "Go to", keywords: ["certificates"] },
  { id: "go-notifications", label: "Notifications", path: "/notifications", icon: <Bell className={ICON} />, group: "Go to", keywords: ["whatsapp", "alerts"] },
  { id: "go-sources", label: "Data sources", path: "/sources", icon: <Database className={ICON} />, group: "Go to" },
  { id: "go-team", label: "Team", path: "/settings/team", icon: <Users className={ICON} />, group: "Go to", keywords: ["members", "roles"] },
  { id: "f-closing", label: "Closing within 7 days", path: "/tenders?closing_within=7&sort=deadline", icon: <CalendarClock className={ICON} />, group: "Filters" },
  { id: "f-eligible", label: "Eligible tenders", path: "/tenders?eligibility=ELIGIBLE", icon: <CheckCircle2 className={ICON} />, group: "Filters" },
  { id: "f-verify", label: "Needs verification", path: "/tenders?action=verify", icon: <ShieldAlert className={ICON} />, group: "Filters", keywords: ["evidence", "missing"] },
  { id: "a-import", label: "Import tender", path: "/sources#import", icon: <FileUp className={ICON} />, group: "Actions", keywords: ["csv", "nit", "pdf", "upload"] },
  { id: "a-certificate", label: "Add certificate", path: "/company/documents", icon: <FileCheck2 className={ICON} />, group: "Actions", keywords: ["upload", "gst", "registration"] },
  { id: "a-invite", label: "Invite member", path: "/settings/team", icon: <UserPlus className={ICON} />, group: "Actions" },
];

const THEME_ITEM: CommandItem = {
  id: "theme",
  label: "Change theme",
  icon: <SunMoon className={ICON} />,
  group: "Actions",
  keywords: ["dark", "light", "appearance"],
  placeholder: "Choose a theme…",
  children: [
    { id: "theme-light", label: "Light", icon: <SunMoon className={ICON} /> },
    { id: "theme-dark", label: "Dark", icon: <SunMoon className={ICON} /> },
    { id: "theme-system", label: "Match system", icon: <SunMoon className={ICON} /> },
  ],
};

function CommandPalette() {
  const router = useRouter();
  const { setTheme } = useTheme();
  const tenders = useQuery({
    queryKey: ["tenders", "palette"],
    queryFn: () => api<TenderList>("/api/v1/tenders?page_size=100&include_closed=true"),
    staleTime: 60_000,
  });
  const routes = useMemo(() => {
    const map = new Map<string, string>(PAGES.map((p) => [p.id, p.path]));
    for (const t of tenders.data?.items ?? []) map.set(`tender-${t.id}`, `/tenders/${t.id}`);
    return map;
  }, [tenders.data]);
  const items = useMemo<CommandItem[]>(
    () => [
      ...PAGES.map((p) => ({ id: p.id, label: p.label, icon: p.icon, group: p.group, keywords: p.keywords })),
      THEME_ITEM,
      ...(tenders.data?.items ?? []).map((t) => ({
        id: `tender-${t.id}`,
        label: t.title,
        icon: <Search className={ICON} />,
        group: "Tenders",
        keywords: [t.reference_number ?? "", t.district ?? "", t.issuing_organization ?? "", t.department ?? ""].filter(Boolean),
      })),
    ],
    [tenders.data],
  );

  return (
    <ActionSearchBar
      className="max-w-lg"
      items={items}
      defaultRecent={[]}
      shortcut
      label="Search TenderOS"
      placeholder="Search tenders, pages and actions…"
      onSelect={(item) => {
        if (item.id.startsWith("theme-")) {
          setTheme(item.id.slice(6));
          return;
        }
        const path = routes.get(item.id);
        if (path) router.push(path);
      }}
    />
  );
}

function AccountMenu({ me }: { me: Me }) {
  const qc = useQueryClient();
  const router = useRouter();
  const logout = useLogout();
  const { theme, setTheme } = useTheme();
  const accounts = me.companies.map((c) => ({ id: c.id, name: c.name, email: me.user.email, plan: titleCase(c.role) }));

  return (
    <ProfileDropdown
      key={me.active_company?.id}
      accounts={accounts}
      defaultAccountId={me.active_company?.id}
      onAccountChange={async (account) => {
        await api<Me>("/api/v1/auth/switch-company", { method: "POST", json: { organization_id: account.id } });
        qc.clear();
        router.replace("/dashboard");
      }}
      items={[
        { label: "Company profile", icon: <Building2 className="size-4" />, onSelect: () => router.push("/company") },
        { label: "Notifications", icon: <Bell className="size-4" />, onSelect: () => router.push("/notifications") },
        { label: "Team", icon: <Users className="size-4" />, onSelect: () => router.push("/settings/team") },
      ]}
      theme={(theme as "light" | "dark" | "system" | undefined) ?? "system"}
      onThemeChange={setTheme}
      showStatus={false}
      onSignOut={() => logout.mutate()}
    />
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const me = useMe();
  const router = useRouter();
  const pathname = usePathname();
  const { resolvedTheme, setTheme } = useTheme();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (me.error instanceof ApiError && me.error.status === 401) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [me.error, pathname, router]);

  if (!me.data) {
    return (
      <div className="grid min-h-dvh place-items-center text-sm text-muted" aria-busy="true">
        {me.error && !(me.error instanceof ApiError && me.error.status === 401) ? "Could not reach the TenderOS API." : "Loading…"}
      </div>
    );
  }

  const onboarding = me.data.active_company && !me.data.active_company.onboarding_complete && pathname !== "/onboarding";

  return (
    <div className="min-h-dvh lg:pl-64">
      <div
        aria-hidden
        className="pointer-events-none fixed inset-x-0 top-0 -z-10 h-[480px] bg-[radial-gradient(50%_70%_at_75%_0%,color-mix(in_oklab,var(--accent)_13%,transparent),transparent),radial-gradient(35%_50%_at_30%_0%,color-mix(in_oklab,#8b5cf6_9%,transparent),transparent)]"
      />
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2">
        Skip to content
      </a>
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-line bg-surface/60 backdrop-blur-xl lg:block">
        <Sidebar me={me.data} />
      </aside>
      {mobileOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button type="button" aria-label="Close menu" className="absolute inset-0 bg-black/40" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 border-r border-line bg-canvas">
            <button type="button" className="absolute right-3 top-4 rounded p-1 text-muted" aria-label="Close menu" onClick={() => setMobileOpen(false)}>
              <X className="size-4" />
            </button>
            <Sidebar me={me.data} onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      ) : null}

      <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-line/70 bg-canvas/70 px-4 backdrop-blur-xl lg:px-8">
        <button type="button" className="rounded-lg p-2 text-muted hover:bg-subtle lg:hidden" aria-label="Open menu" onClick={() => setMobileOpen(true)}>
          <Menu className="size-4" />
        </button>
        <div className="min-w-0 flex-1">
          <CommandPalette />
        </div>
        <SwitchButton
          size="sm"
          showLabel={false}
          theme={resolvedTheme === "dark" ? "dark" : resolvedTheme === "light" ? "light" : undefined}
          onThemeChange={setTheme}
          className="rounded-xl"
        />
        <AccountMenu me={me.data} />
      </header>

      {onboarding ? (
        <div className="border-b border-warn-line bg-warn-soft px-4 py-2.5 text-xs text-warn lg:px-8">
          Company setup is incomplete (step {Math.min(me.data.active_company!.onboarding_step, 5)} of 5). Eligibility stays “Needs verification” until your profile has evidence.{" "}
          <Link href="/onboarding" className="font-semibold underline underline-offset-4">
            Continue setup
          </Link>
        </div>
      ) : null}

      <main id="main" className="mx-auto max-w-[1440px] px-4 py-8 lg:px-8">
        {me.data.active_company ? (
          children
        ) : (
          <p className="text-sm text-muted">You are not a member of any company. Ask an owner for an invitation link.</p>
        )}
      </main>
    </div>
  );
}
