"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";

import { CertificateForm, CertificateTable } from "@/components/company/certificates";
import { BusinessForm, CapacityForm, ExperienceManager, GeographyForm, WorkCategoriesForm } from "@/components/company/profile-forms";
import { STEPS, Stepper } from "@/components/company/stepper";
import { NotificationPrefsForm } from "@/components/notifications/prefs-form";
import { Button } from "@/components/ui/button";
import { ErrorState, PageHeader, Skeleton } from "@/components/ui/display";
import { api } from "@/lib/api";
import { canEdit, useProfile, useSaveProfile } from "@/lib/hooks";
import type { NotificationPrefs } from "@/lib/types";

function Wizard() {
  const router = useRouter();
  const params = useSearchParams();
  const profile = useProfile();
  const save = useSaveProfile();
  const prefs = useQuery({ queryKey: ["notification-prefs"], queryFn: () => api<NotificationPrefs>("/api/v1/notifications/preferences") });
  const [adding, setAdding] = useState(false);

  if (profile.isLoading) return <Skeleton className="h-96 w-full" />;
  if (profile.error || !profile.data) return <ErrorState message="Could not load your company profile." onRetry={() => void profile.refetch()} />;

  const p = profile.data;
  const completedUpTo = Math.min(Math.max(p.onboarding_step, 1), 5);
  const requested = Number(params.get("step"));
  const step = requested >= 1 && requested <= completedUpTo ? requested : completedUpTo;
  const go = (n: number) => router.replace(`/onboarding?step=${n}`, { scroll: false });
  const readOnly = !canEdit(p.role, "admin");
  const later = (
    <Button asChild variant="quiet">
      <Link href="/dashboard">Save &amp; finish later</Link>
    </Button>
  );
  const next = (n: number) => () => go(Math.min(n + 1, 5));

  async function finish() {
    try {
      await save.mutateAsync({ complete: true, step: 5 });
      toast.success("Setup complete. Eligibility recomputed for every tender.");
      router.replace("/dashboard");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not finish setup");
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
      <aside>
        <Stepper current={step} completedUpTo={completedUpTo} onSelect={go} />
        <p className="mt-4 px-2.5 text-2xs text-muted">Each step saves on its own. You can stop at any point and continue later.</p>
      </aside>
      <section aria-labelledby="step-title" className="rounded-lg border border-line bg-surface">
        <header className="border-b border-line px-5 py-4">
          <p className="section-label">
            Step {step} of 5
          </p>
          <h2 id="step-title" className="mt-0.5 text-base font-semibold">
            {STEPS[step - 1]!.title}
          </h2>
        </header>
        <div className="px-5 py-5">
          {step === 1 ? <BusinessForm key="s1" profile={p} step={2} submitLabel="Save & continue" onSaved={next(1)} secondary={later} readOnly={readOnly} /> : null}
          {step === 2 ? <WorkCategoriesForm key="s2" profile={p} step={3} submitLabel="Save & continue" onSaved={next(2)} secondary={later} readOnly={readOnly} /> : null}
          {step === 3 ? <GeographyForm key="s3" profile={p} step={4} submitLabel="Save & continue" onSaved={next(3)} secondary={later} readOnly={readOnly} /> : null}
          {step === 4 ? (
            <div className="space-y-6">
              <CapacityForm key="s4" profile={p} step={5} submitLabel="Save & continue" onSaved={next(4)} secondary={later} readOnly={readOnly} />
              <div>
                <h3 className="mb-2 text-sm font-semibold">Similar completed projects</h3>
                <ExperienceManager profile={p} readOnly={readOnly} />
              </div>
            </div>
          ) : null}
          {step === 5 ? (
            <div className="space-y-6">
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-sm font-semibold">Registration, experience & financial certificates</h3>
                  {!readOnly && !adding ? (
                    <Button size="sm" onClick={() => setAdding(true)}>
                      Add certificate
                    </Button>
                  ) : null}
                </div>
                {adding ? (
                  <div className="mb-4 rounded-md border border-line bg-subtle/40 p-3">
                    <CertificateForm onDone={() => setAdding(false)} />
                  </div>
                ) : null}
                <CertificateTable certificates={p.certificates} canManage={!readOnly} />
              </div>
              <div>
                <h3 className="mb-2 text-sm font-semibold">Alert preferences</h3>
                {prefs.data ? <NotificationPrefsForm prefs={prefs.data} /> : <Skeleton className="h-40 w-full" />}
              </div>
              <div className="flex flex-wrap items-center justify-end gap-2 border-t border-line pt-4">
                {later}
                <Button variant="primary" onClick={() => void finish()} disabled={readOnly || save.isPending}>
                  Finish setup
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}

export default function OnboardingPage() {
  return (
    <>
      <PageHeader
        eyebrow="Let's get you set up"
        title="Tell TenderOS what your company can bid on"
        description="A few minutes here and every tender gets checked against your real turnover, registrations and experience. No guesswork."
      />
      <Suspense>
        <Wizard />
      </Suspense>
    </>
  );
}
