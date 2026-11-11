import { FileSearch, Scale, ShieldCheck } from "lucide-react";

import TopoBackground from "@/components/kokonutui/topo-background";

const POINTS = [
  { icon: FileSearch, title: "Know before you bid", body: "Every criterion checked against your certificates, with the exact NIT page and clause." },
  { icon: Scale, title: "Scores that don't lie", body: "A great match never hides a mandatory failure." },
  { icon: ShieldCheck, title: "Straight from the source", body: "Official portals only. No shady scraped feeds." },
];

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <span className="grid size-8 rotate-[-6deg] place-items-center rounded-xl bg-gradient-to-br from-accent to-[#8b5cf6] font-display text-sm font-bold text-white shadow-[0_6px_16px_-6px_var(--accent)]">
        T
      </span>
      <span className="font-display text-lg font-semibold tracking-[-0.02em]">TenderOS</span>
    </div>
  );
}

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-dvh bg-surface lg:grid-cols-[minmax(0,1.15fr)_minmax(460px,1fr)]">
      {/* Contour lines take the text colour of the root, so text-accent tints the map. */}
      <TopoBackground className="hidden min-h-dvh items-stretch bg-canvas text-accent lg:flex" labels={false} speed={0.6} seed={23}>
        <div className="relative flex w-full flex-col justify-between p-12 text-ink xl:p-16">
          <Logo />

          <div className="max-w-lg">
            <p className="mb-4 text-sm font-medium text-accent">Built for Madhya Pradesh contractors</p>
            <h2 className="text-balance text-[2.5rem] font-semibold leading-[1.08] tracking-[-0.035em]">
              Stop guessing. Bid on the tenders you can <span className="text-accent">actually win</span>.
            </h2>
            <ul className="mt-10 space-y-5">
              {POINTS.map(({ icon: Icon, title, body }) => (
                <li key={title} className="flex gap-4">
                  <span className="grid size-9 shrink-0 place-items-center rounded-xl border border-line bg-surface/80 text-accent shadow-card backdrop-blur-sm">
                    <Icon className="size-4" aria-hidden />
                  </span>
                  <span>
                    <span className="block text-sm font-medium">{title}</span>
                    <span className="mt-0.5 block text-sm text-muted">{body}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <p className="text-2xs text-muted">Madhya Pradesh · All times in IST</p>
        </div>
      </TopoBackground>

      <main className="flex min-h-dvh flex-col border-line px-6 py-8 sm:px-12 lg:border-l">
        <div className="lg:hidden">
          <Logo />
        </div>
        <div className="flex flex-1 items-center justify-center py-12">
          <div className="w-full max-w-[22rem]">{children}</div>
        </div>
        <p className="text-center text-2xs text-faint">TenderOS does not guarantee acceptance by any procuring authority.</p>
      </main>
    </div>
  );
}
