import { Suspense } from "react";

import { TenderExplorer } from "@/components/tenders/explorer";
import { PageHeader } from "@/components/ui/display";

export const metadata = { title: "Tender explorer" };

export default function TendersPage() {
  return (
    <>
      <PageHeader
        title="Find your next win"
        description="Search, filter and sort every tender you can see. Your filters live in the URL, so share a link and your team sees the same list."
      />
      <Suspense>
        <TenderExplorer />
      </Suspense>
    </>
  );
}
