import io

import pymupdf
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Organization, SourceProvider, Tender, User
from app.services.extraction.nit import PageText, extract_nit, extract_requirements
from app.services.extraction.readers import pdf_pages, read_boq
from app.services.ingestion.document_import import import_document
from app.services.uploads import validate_upload

NIT_PAGE_1 = """Notice Inviting Tender
Tender ID: 2026_PWDRB_555001_1
Name of Work: Construction of BT road from Sagar to Rahatgarh km 4 to 12
Department: Public Works Department (Roads & Bridges)
Estimated Cost: Rs. 3.40 Crore
EMD: Rs. 3,40,000/-
Bid Submission End Date: 28-12-2026 17:30
Period of Completion: 9 Months"""

NIT_PAGE_2 = """3. Eligibility
3.1 Average annual turnover during the last 3 financial years shall not be less than Rs. 170.00 lakh.
3.2 The bidder should have completed one similar work of value not less than Rs. 136.00 lakh.
3.3 Bidder must be registered in Class C or above with MP PWD.
3.4 Valid GST registration certificate shall be uploaded.
3.5 Solvency certificate of Rs. 34 lakh from a scheduled bank."""


def _pdf() -> bytes:
    doc = pymupdf.open()
    for text in (NIT_PAGE_1, NIT_PAGE_2):
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def test_pdf_extraction_cites_page_clause_and_quote() -> None:
    pages = pdf_pages(_pdf())
    result = extract_nit(pages, "nit.pdf")
    m = result.metadata
    assert m["tender_id"] == "2026_PWDRB_555001_1"
    assert m["estimated_value_paise"] == 3_40_00_000_00
    assert m["district"] == "Sagar" and m["category_code"] == "roads"
    assert m["completion_period_days"] == 270
    by_type = {r.requirement_type: r for r in result.requirements}
    assert by_type["annual_turnover"].threshold_value == 1_70_00_000_00
    assert by_type["similar_work"].threshold_value == 1_36_00_000_00
    assert by_type["contractor_registration"].threshold_text == "C"
    assert by_type["solvency"].threshold_value == 34_00_000_00
    assert any(r.threshold_text == "gst" for r in result.requirements)
    for r in result.requirements:
        assert r.page_number == 2 and r.evidence_quote and r.document_ref == "nit.pdf"
        assert r.verification_status == "needs_review" and r.extraction_method == "deterministic"
    assert by_type["annual_turnover"].clause_ref == "3.1"


def test_hindi_requirement_extraction() -> None:
    page = PageText(3, "2(क) निविदाकार का पिछले तीन वर्षों का औसत वार्षिक टर्नओवर ₹ 150.00 लाख से कम नहीं होना चाहिए।\n"
                       "म.प्र. लो.नि.वि. में श्रेणी 'C' या उससे ऊपर का पंजीयन अनिवार्य।")
    reqs = extract_requirements([page], "nit-hi.pdf", None, "roads")
    kinds = {r.requirement_type: r for r in reqs}
    assert kinds["annual_turnover"].threshold_value == 1_50_00_000_00
    assert kinds["contractor_registration"].threshold_text == "C"
    assert all(r.page_number == 3 for r in reqs)


def test_boq_reader_sums_amounts_without_formulas() -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(["Bill of Quantities"])
    ws.append(["Item No", "Description of item", "Unit", "Quantity", "Rate", "Amount"])
    ws.append(["1", "Earthwork in excavation", "cum", 1200, 180, None])
    ws.append(["2", "DBM 50 mm", "cum", 300, 9500, 2850000])
    ws.append([None, "Total", None, None, None, "=SUM(F3:F4)"])
    buf = io.BytesIO()
    wb.save(buf)
    summary = read_boq(buf.getvalue())
    assert summary["item_count"] == 3
    assert summary["total_paise"] == (1200 * 180 + 2850000) * 100


def test_document_import_creates_private_tender_for_review(seeded: Session) -> None:
    db = seeded
    org = db.scalar(select(Organization).where(Organization.legal_name.like("Narmada%")))
    user = db.scalar(select(User).where(User.email == "analyst@narmada.demo"))
    src = db.scalar(select(SourceProvider).where(SourceProvider.code == "manual_document"))
    up = validate_upload("nit.pdf", _pdf(), {"pdf"})
    res = import_document(db, src, up, kind="nit", organization_id=org.id, user_id=user.id, tender=None,
                          overrides={"source_url": "https://mptenders.gov.in/"})
    db.commit()
    t = db.get(Tender, res.tender_id)
    assert t.visibility_org_id == org.id and t.retrieval_method == "manual_document"
    assert t.original_file_sha256 == up.sha256 and t.documents_available
    assert res.requirements_extracted == 5
    assert all(r.document_id == res.document_id for r in t.requirements)
