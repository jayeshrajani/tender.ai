import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { vi } from "vitest";

import type { Me, TenderDetail, TenderRow } from "@/lib/types";

export function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

type Handler = (url: string, init?: RequestInit) => unknown;

/** Route fetch calls by URL prefix; returns the spy so tests can assert on requests. */
export function mockFetch(routes: Record<string, unknown | Handler>) {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const key = Object.keys(routes)
      .sort((a, b) => b.length - a.length)
      .find((k) => url.startsWith(k));
    if (!key) return new Response(JSON.stringify({ detail: `unmocked ${url}` }), { status: 404 });
    const value = routes[key];
    const body = typeof value === "function" ? (value as Handler)(url, init) : value;
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

export const ME: Me = {
  user: { id: "u1", email: "analyst@narmada.demo", full_name: "Priya Sharma (DEMO)" },
  active_company: { id: "o1", name: "Narmada Buildcon Pvt. Ltd. (DEMO)", role: "analyst", onboarding_step: 6, onboarding_complete: true, is_demo: true },
  companies: [{ id: "o1", name: "Narmada Buildcon Pvt. Ltd. (DEMO)", role: "analyst" }],
};

export function row(over: Partial<TenderRow> = {}): TenderRow {
  return {
    id: "t1",
    title: "Strengthening and widening of Bhopal–Berasia road",
    reference_number: "DEMO/2026_PWDRB_418203_1",
    department: "Public Works Department (Roads & Bridges)",
    issuing_organization: "PWD Division No. 1, Bhopal",
    district: "Bhopal",
    category_code: "roads",
    estimated_value_paise: 12_40_00_000_00,
    published_at: "2026-11-02T05:00:00Z",
    deadline: "2026-11-23T12:00:00Z",
    previous_deadline: null,
    deadline_changed_at: null,
    status: "active",
    is_demo: true,
    retrieval_method: "demo_fixture",
    documents_available: false,
    eligibility_status: "NOT_ELIGIBLE",
    eligibility_summary: "Fails: 1 similar completed work ≥ ₹9.92 Cr each.",
    mandatory_failures: 1,
    unknown_count: 0,
    relevance_score: 85.47,
    saved_state: null,
    action: "not_eligible",
    ...over,
  };
}

export function detail(over: Partial<TenderDetail> = {}): TenderDetail {
  return {
    ...row(),
    source_tender_id: "DEMO-2026-001",
    location: "Berasia Road, Bhopal",
    subcategory_codes: [],
    tender_type: "Open / Item rate",
    emd_paise: 12_40_000_00,
    tender_fee_paise: 10_000_00,
    completion_period_days: 360,
    bid_submission_start_at: null,
    bid_opening_at: "2026-11-24T05:30:00Z",
    pre_bid_meeting_at: null,
    nit_summary: "Two-lane widening.",
    version: 1,
    provenance: {
      source_name: "DEMO tender fixtures",
      source_code: "demo_fixture",
      source_url: "https://mptenders.gov.in/nicgep/app?page=FrontEndLatestActiveTenders&service=page",
      source_organization: "DEMO fixture",
      retrieval_method: "demo_fixture",
      permission_status: "not_required_demo",
      imported_at: "2026-11-11T03:00:00Z",
      imported_by: null,
      original_file_sha256: null,
      last_seen_at: "2026-11-11T03:00:00Z",
      is_private_import: false,
    },
    also_seen_in: [],
    documents: [],
    versions: [],
    timeline: [{ at: "2026-11-23T12:00:00Z", kind: "deadline", label: "Bid submission closes" }],
    eligibility: {
      status: "NOT_ELIGIBLE",
      summary: "Fails: 1 similar completed work ≥ ₹9.92 Cr each.",
      mandatory_failures: 1,
      unknown_count: 1,
      computed_at: "2026-11-11T03:00:00Z",
      disclaimer: "Indicative check. It does not guarantee acceptance by the procuring authority.",
      requirements: [
        {
          id: "r1",
          requirement_type: "annual_turnover",
          label: "Average annual turnover ≥ ₹6.20 Cr (last 3 FY)",
          mandatory: true,
          operator: "gte",
          threshold_value: 6_20_00_000_00,
          threshold_text: null,
          unit: "paise",
          period_years: 3,
          citation: { document: "NIT (DEMO)", document_id: null, page: 4, clause: "3.1(a)", quote: "Average annual financial turnover … Rs. 620.00 lakh." },
          extraction_method: "seed",
          verification_status: "source_verified",
          result: "PASS",
          explanation: "Turnover ₹18.00 Cr ≥ ₹6.20 Cr; CA-certified turnover verified.",
          company_evidence: [{ kind: "certificate", id: "c1", title: "CA-certified turnover", verification_status: "verified" }],
        },
        {
          id: "r2",
          requirement_type: "similar_work",
          label: "1 similar completed work ≥ ₹9.92 Cr each",
          mandatory: true,
          operator: "gte",
          threshold_value: 9_92_00_000_00,
          threshold_text: "1",
          unit: "paise",
          period_years: null,
          citation: { document: "NIT (DEMO)", document_id: null, page: 4, clause: "3.1(b)", quote: "at least one similar work of value not less than Rs. 992.00 lakh" },
          extraction_method: "seed",
          verification_status: "source_verified",
          result: "FAIL",
          explanation: "Needs 1 similar work of at least ₹9.92 Cr; recorded experience has 0.",
          company_evidence: [],
        },
        {
          id: "r3",
          requirement_type: "certificate",
          label: "EPF registration",
          mandatory: true,
          operator: "exists",
          threshold_value: null,
          threshold_text: "epf",
          unit: "none",
          period_years: null,
          citation: { document: "NIT (DEMO)", document_id: null, page: 5, clause: "3.5", quote: "Proof of EPF registration shall be uploaded." },
          extraction_method: "seed",
          verification_status: "source_verified",
          result: "UNKNOWN",
          explanation: "No EPF registration on file.",
          company_evidence: [],
        },
      ],
    },
    relevance: {
      score: 85.47,
      breakdown: [
        { key: "specialization", label: "Specialisation match", weight: 25, fraction: 1, points: 25, reason: "Matches your category." },
        { key: "location", label: "Location match", weight: 15, fraction: 1, points: 15, reason: "Bhopal is preferred." },
      ],
    },
    notes: [],
    can_review_requirements: false,
    ...over,
  };
}
