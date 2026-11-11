"use client";

import Link from "next/link";

import { BusinessForm, CapacityForm, ExperienceManager, GeographyForm, WorkCategoriesForm } from "@/components/company/profile-forms";
import { Button } from "@/components/ui/button";
import { ErrorState, PageHeader, Panel, Skeleton } from "@/components/ui/display";
import { canEdit, useProfile } from "@/lib/hooks";

export default function CompanyPage() {
  const profile = useProfile();
  if (profile.isLoading) return <Skeleton className="h-96 w-full" />;
  if (profile.error || !profile.data) return <ErrorState message="Could not load company profile." onRetry={() => void profile.refetch()} />;
  const p = profile.data;
  const readOnly = !canEdit(p.role, "admin");
  return (
    <>
      <PageHeader
        title="Company profile"
        description="What you build, where and how big. Change anything and every tender re-scores instantly."
        actions={
          <Button asChild>
            <Link href="/company/documents">Document vault</Link>
          </Button>
        }
      />
      <div className="grid gap-6 xl:grid-cols-2">
        <Panel id="legal" title="Legal details">
          <BusinessForm profile={p} submitLabel="Save legal details" readOnly={readOnly} />
        </Panel>
        <Panel id="work" title="Work categories">
          <WorkCategoriesForm profile={p} submitLabel="Save categories" readOnly={readOnly} />
        </Panel>
        <Panel id="geo" title="Districts & operational preferences">
          <GeographyForm profile={p} submitLabel="Save preferences" readOnly={readOnly} />
        </Panel>
        <Panel id="capacity" title="Turnover, registration & capacity">
          <CapacityForm profile={p} submitLabel="Save capacity" readOnly={readOnly} />
        </Panel>
        <Panel id="experience" title="Experience" description="Similar completed works with completion certificates." className="xl:col-span-2">
          <ExperienceManager profile={p} readOnly={readOnly} />
        </Panel>
      </div>
    </>
  );
}
