import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BusinessForm } from "@/components/company/profile-forms";
import { EligibilityMatrix, ScoreBreakdown } from "@/components/tenders/eligibility";
import { TenderExplorer } from "@/components/tenders/explorer";
import { TenderTable } from "@/components/tenders/tender-table";
import type { Profile } from "@/lib/types";

import { detail, ME, mockFetch, renderWithClient, row } from "./utils";

const nav = vi.hoisted(() => ({
  replace: vi.fn(),
  push: vi.fn(),
  pathname: "/tenders",
  search: "",
  params: { id: "t1" } as Record<string, string>,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: nav.replace, push: nav.push }),
  usePathname: () => nav.pathname,
  useSearchParams: () => new URLSearchParams(nav.search),
  useParams: () => nav.params,
}));

beforeEach(() => {
  nav.replace.mockReset();
  nav.push.mockReset();
  nav.pathname = "/tenders";
  nav.search = "";
});

describe("navigation", () => {
  it("marks the active route and exposes all main sections", async () => {
    const { Sidebar } = await import("@/components/app-shell");
    nav.pathname = "/sources";
    mockFetch({});
    renderWithClient(<Sidebar me={ME} />);
    const main = screen.getByRole("navigation", { name: "Main" });
    for (const label of ["Dashboard", "Tender explorer", "Saved tenders", "Company profile", "Document vault", "Notifications", "Data sources", "Team"]) {
      expect(within(main).getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(within(main).getByRole("link", { name: "Data sources" })).toHaveAttribute("aria-current", "page");
    expect(within(main).getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
    expect(screen.getByText(/Nothing here is live government data/)).toBeInTheDocument();
  });
});

describe("tender table", () => {
  it("renders the required columns, DEMO label and eligibility", () => {
    mockFetch({});
    renderWithClient(<TenderTable rows={[row()]} caption="Tenders" sort="relevance" order="desc" onSort={() => {}} />);
    const table = screen.getByRole("table", { name: "Tenders" });
    for (const h of ["Tender", "Issuing organisation", "District", "Est. value", "Submission deadline", "Eligibility", "Relevance"]) {
      expect(within(table).getByRole("columnheader", { name: new RegExp(h) })).toBeInTheDocument();
    }
    expect(within(table).getByText("₹12.40 Cr")).toBeInTheDocument();
    expect(within(table).getAllByText("DEMO").length).toBeGreaterThan(0);
    expect(within(table).getByText("Not eligible")).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: /Relevance/ })).toHaveAttribute("aria-sort", "descending");
  });

  it("calls onSort when a sortable header is clicked", async () => {
    mockFetch({});
    const onSort = vi.fn();
    renderWithClient(<TenderTable rows={[row()]} caption="Tenders" sort="relevance" order="desc" onSort={onSort} />);
    await userEvent.click(screen.getByRole("button", { name: /Submission deadline/ }));
    expect(onSort).toHaveBeenCalledWith("deadline");
  });

  it("renders the empty state when there are no rows", () => {
    renderWithClient(<TenderTable rows={[]} caption="Tenders" empty={<p>Nothing matches</p>} />);
    expect(screen.getByText("Nothing matches")).toBeInTheDocument();
  });
});

describe("tender explorer filtering and sorting", () => {
  function setup(search = "") {
    nav.search = search;
    return mockFetch({
      "/api/v1/auth/me": ME,
      "/api/v1/tenders/facets": { districts: [{ value: "Bhopal", count: 6 }, { value: "Sehore", count: 4 }], categories: [{ value: "roads", count: 7 }] },
      "/api/v1/views": { items: [] },
      "/api/v1/tenders": (url: string) => ({
        items: url.includes("district=Sehore") ? [row({ id: "t2", district: "Sehore", title: "PMGSY roads Sehore" })] : [row()],
        total: 1,
        page: 1,
        page_size: 25,
        sort: "relevance",
        order: "desc",
        generated_at: "2026-11-11T03:00:00Z",
      }),
    });
  }

  it("passes URL filters to the API", async () => {
    const fetchSpy = setup("district=Sehore&sort=deadline");
    renderWithClient(<TenderExplorer />);
    expect((await screen.findAllByText("PMGSY roads Sehore")).length).toBeGreaterThan(0);
    const listCall = fetchSpy.mock.calls.map((c) => String(c[0])).find((u) => u.startsWith("/api/v1/tenders?"));
    expect(listCall).toContain("district=Sehore");
    expect(listCall).toContain("sort=deadline");
  });

  it("writes multi-select filter changes to the URL", async () => {
    setup();
    renderWithClient(<TenderExplorer />);
    await screen.findAllByText(/Bhopal–Berasia/);
    await userEvent.click(screen.getByRole("button", { name: /^District/ }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /^Sehore/ }));
    expect(nav.replace).toHaveBeenLastCalledWith("/tenders?district=Sehore", { scroll: false });
  });

  it("toggles quick filters and sort through the URL", async () => {
    setup();
    renderWithClient(<TenderExplorer />);
    await screen.findAllByText(/Bhopal–Berasia/);
    await userEvent.click(screen.getByRole("button", { name: "Closing ≤ 7 days" }));
    expect(nav.replace).toHaveBeenLastCalledWith("/tenders?closing_within=7", { scroll: false });
    await userEvent.click(screen.getByRole("button", { name: /Est\. value/ }));
    expect(nav.replace).toHaveBeenLastCalledWith("/tenders?sort=value", { scroll: false });
  });

  it("debounces search into the URL", async () => {
    setup();
    renderWithClient(<TenderExplorer />);
    await screen.findAllByText(/Bhopal–Berasia/);
    await userEvent.type(screen.getByRole("searchbox", { name: "Search tenders" }), "bridge");
    await waitFor(() => expect(nav.replace).toHaveBeenLastCalledWith("/tenders?q=bridge", { scroll: false }));
  });
});

describe("eligibility display", () => {
  it("shows PASS / FAIL / NEEDS VERIFICATION with page and clause citations", () => {
    mockFetch({});
    renderWithClient(<EligibilityMatrix tender={detail()} />);
    const list = screen.getByRole("list", { name: /Eligibility criteria/ });
    const rows = within(list).getAllByRole("listitem").filter((li) => li.parentElement === list);
    expect(within(rows[0]!).getByText("PASS")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("FAIL")).toBeInTheDocument();
    expect(within(rows[2]!).getByText("NEEDS VERIFICATION")).toBeInTheDocument();
    expect(within(rows[1]!).getByText(/Page 4 · Clause 3\.1\(b\)/)).toBeInTheDocument();
    expect(within(rows[1]!).getByText(/not less than Rs\. 992\.00 lakh/)).toBeInTheDocument();
    expect(within(rows[0]!).getByText("CA-certified turnover")).toBeInTheDocument();
  });

  it("refuses to show criteria when no source document exists", () => {
    mockFetch({});
    renderWithClient(<EligibilityMatrix tender={detail({ eligibility: { ...detail().eligibility, requirements: [] } })} />);
    expect(screen.getByText("No eligibility criteria extracted")).toBeInTheDocument();
    expect(screen.getByText(/does not guess criteria/)).toBeInTheDocument();
  });

  it("shows the weighted relevance breakdown", () => {
    renderWithClient(<ScoreBreakdown factors={detail().relevance.breakdown} score={85.47} />);
    expect(screen.getByText("85")).toBeInTheDocument();
    expect(screen.getByText("Specialisation match")).toBeInTheDocument();
    expect(screen.getByText(/independent of eligibility/)).toBeInTheDocument();
  });
});

describe("tender detail page", () => {
  it("renders title, official link, DEMO notice and eligibility evidence", async () => {
    nav.params = { id: "t1" };
    mockFetch({ "/api/v1/auth/me": ME, "/api/v1/tenders/t1": detail() });
    const { default: Page } = await import("@/app/(app)/tenders/[id]/page");
    renderWithClient(<Page />);
    expect(await screen.findByRole("heading", { level: 1, name: /Bhopal–Berasia/ })).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Official portal/ });
    expect(link).toHaveAttribute("href", expect.stringContaining("mptenders.gov.in"));
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByText(/DEMO record\./)).toBeInTheDocument();
    expect(screen.getByRole("list", { name: /Eligibility criteria/ })).toBeInTheDocument();
    expect(screen.getByText("Relevance breakdown")).toBeInTheDocument();
  });
});

describe("onboarding", () => {
  const profile = {
    id: "o1",
    legal_name: "New Infra",
    business_type: null,
    gstin: null,
    pan: null,
    contact_name: null,
    contact_email: null,
    contact_phone: null,
    address: null,
    base_district: null,
    role: "owner",
  } as unknown as Profile;

  it("validates GSTIN/PAN and saves the step with normalised values", async () => {
    const fetchSpy = mockFetch({
      "/api/v1/company/reference": { categories: [], districts: ["Bhopal"], registration_classes: [], business_types: ["proprietorship"], certificate_types: [] },
      "/api/v1/company/profile": (_url: string, init?: RequestInit) => ({ ...profile, ...(init?.body ? JSON.parse(String(init.body)) : {}) }),
    });
    const onSaved = vi.fn();
    renderWithClient(<BusinessForm profile={profile} step={2} submitLabel="Save & continue" onSaved={onSaved} />);
    await screen.findByRole("option", { name: "Proprietorship" });
    await userEvent.selectOptions(screen.getByLabelText(/Business type/), "proprietorship");
    await userEvent.type(screen.getByLabelText("GSTIN"), "12345");
    await userEvent.click(screen.getByRole("button", { name: "Save & continue" }));
    expect(await screen.findByText(/GSTIN must be 15 characters/)).toBeInTheDocument();
    expect(screen.getByLabelText("GSTIN")).toHaveAttribute("aria-invalid", "true");
    expect(onSaved).not.toHaveBeenCalled();

    await userEvent.clear(screen.getByLabelText("GSTIN"));
    await userEvent.type(screen.getByLabelText("GSTIN"), "23abcde1234f1z5");
    await userEvent.click(screen.getByRole("button", { name: "Save & continue" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const put = fetchSpy.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === "PUT");
    const body = JSON.parse(String((put![1] as RequestInit).body));
    expect(body).toMatchObject({ gstin: "23ABCDE1234F1Z5", business_type: "proprietorship", step: 2, pan: null });
    expect((put![1] as RequestInit).headers).toMatchObject({ "X-Requested-With": "tenderos" });
  });
});
