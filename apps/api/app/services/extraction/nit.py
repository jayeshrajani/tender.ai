"""Deterministic NIT/corrigendum extraction (English + Hindi).

Every extracted requirement carries the document, page, clause and verbatim evidence
quote, and is marked ``needs_review`` so a person confirms it before it can contribute to
an ELIGIBLE result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.services.districts import find_district_in_text
from app.services.ingestion.base import RequirementSpec
from app.services.money import parse_inr
from app.services.taxonomy import classify
from app.services.timeutil import parse_ist_datetime

_AMOUNT = re.compile(
    r"(?:rs\.?|inr|₹|रु\.?)\s*([\d,]+(?:\.\d+)?)\s*(crores?|cr\.?|lakhs?|lacs?|लाख|करोड़)?"
    r"|([\d,]+(?:\.\d+)?)\s*(crores?|cr\.?|lakhs?|lacs?|लाख|करोड़)",
    re.I,
)
_PERCENT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
_DATE = re.compile(
    r"(\d{1,2}[-/.](?:\d{1,2}|[A-Za-z]{3})[-/.]\d{4}(?:\s+\d{1,2}:\d{2}(?:\s*[AaPp][Mm])?)?)"
)
_CLAUSE = re.compile(r"^\s*((?:\d+\.)*\d+(?:\s*\([a-zivx]+\))?|\([a-zivx]+\)|[a-z]\))\s+", re.I)
_CLASS = re.compile(r"(?:class|category|श्रेणी)\s*['\"‘’]?\s*\b(AA|A|B|C|D)\b['\"‘’]?", re.I)

_COUNT_WORDS = {
    "one": 1, "two": 2, "three": 3, "एक": 1, "दो": 2, "तीन": 3,
}


@dataclass
class PageText:
    number: int
    text: str


@dataclass
class ExtractedNIT:
    metadata: dict[str, Any] = field(default_factory=dict)
    requirements: list[RequirementSpec] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_ABBREV = re.compile(r"(?:\b(?:rs|no|sr|ltd|pvt|dr|mr|viz|nos|approx|i\.e|e\.g)\.|रु\.)$", re.I)


def _sentences(text: str) -> list[str]:
    # NIT PDFs are line-oriented: split at clause starts, then at sentence ends followed by a new word.
    joined = re.sub(r"[ \t]+", " ", text)
    blocks = re.split(r"\n(?=\s*(?:\d+(?:\.\d+)*|\([a-zivx]+\)|\d+\([^)]+\))\s)", joined)
    out: list[str] = []
    for block in blocks:
        flat = re.sub(r"\s*\n\s*", " ", block).strip()
        pieces = re.split(r"(?<=[.।;])\s+(?=[A-Z\u0900-\u097F(])", flat)
        merged: list[str] = []
        for p in pieces:
            if merged and _ABBREV.search(merged[-1]):
                merged[-1] = f"{merged[-1]} {p}"
            else:
                merged.append(p)
        out.extend(m for m in merged if m)
    return out


def _amount(sentence: str) -> int | None:
    m = _AMOUNT.search(sentence)
    if not m:
        return None
    number = m.group(1) or m.group(3)
    unit = m.group(2) or m.group(4) or ""
    return parse_inr(f"{number} {unit}".strip())


def _percent_of(sentence: str, estimate: int | None) -> int | None:
    m = _PERCENT.search(sentence)
    if not m or not estimate:
        return None
    return int(estimate * float(m.group(1)) / 100)


def _clause(sentence: str) -> str | None:
    m = _CLAUSE.match(sentence)
    return m.group(1).strip() if m else None


def _count(sentence: str) -> int:
    lowered = sentence.lower()
    for word, n in _COUNT_WORDS.items():
        if re.search(rf"(?<!\w){word}(?!\w)", lowered):
            return n
    return 1


def _has(sentence: str, *needles: str) -> bool:
    lowered = sentence.lower()
    return any(n in lowered for n in needles)


def _spec(kind: str, label: str, op: str, sentence: str, page: int, doc_ref: str, **kw: Any) -> RequirementSpec:
    return RequirementSpec(
        requirement_type=kind,
        label=label,
        operator=op,
        document_ref=doc_ref,
        page_number=page,
        clause_ref=_clause(sentence),
        evidence_quote=sentence[:400],
        extraction_method="deterministic",
        verification_status="needs_review",
        **kw,
    )


def extract_requirements(
    pages: list[PageText], doc_ref: str, estimate_paise: int | None, category: str | None
) -> list[RequirementSpec]:
    out: list[RequirementSpec] = []
    seen: set[tuple[Any, ...]] = set()

    def add(spec: RequirementSpec) -> None:
        key = (spec.requirement_type, spec.threshold_value, spec.threshold_text)
        if key not in seen:
            seen.add(key)
            out.append(spec)

    for page in pages:
        for s in _sentences(page.text):
            if _has(s, "turnover", "टर्नओवर", "आवर्त"):
                value = _amount(s) or _percent_of(s, estimate_paise)
                if value:
                    years = 5 if _has(s, "five", "5 years", "5 financial", "पाँच", "पांच") else 3
                    add(_spec("annual_turnover", f"Average annual turnover ≥ {_fmt(value)}", "gte", s,
                              page.number, doc_ref, threshold_value=value, unit="paise", period_years=years))
                continue
            if _has(s, "similar work", "similar nature", "work of similar", "समान प्रकृति", "समान कार्य"):
                value = _amount(s) or _percent_of(s, estimate_paise)
                if value:
                    n = _count(s)
                    add(_spec("similar_work", f"{n} similar completed work(s) ≥ {_fmt(value)} each", "gte", s,
                              page.number, doc_ref, threshold_value=value, threshold_text=str(n),
                              unit="paise", category_code=category))
                continue
            if _has(s, "solvency", "सॉल्वेंसी", "शोधन क्षमता"):
                value = _amount(s) or _percent_of(s, estimate_paise)
                if value:
                    add(_spec("solvency", f"Bank solvency ≥ {_fmt(value)}", "gte", s, page.number, doc_ref,
                              threshold_value=value, unit="paise"))
                continue
            if _has(s, "bid capacity", "बिड क्षमता") or re.search(r"\bA\s*[x×*]\s*N\s*[x×*]\s*2", s):
                add(_spec("bid_capacity", "Available bid capacity ≥ estimated cost", "gte", s, page.number,
                          doc_ref, unit="paise"))
                continue
            m = _CLASS.search(s)
            if m and _has(s, "regist", "पंजीयन", "पंजीकृत"):
                cls = m.group(1).upper()
                add(_spec("contractor_registration", f"Contractor registration Class {cls} or above", "gte",
                          s, page.number, doc_ref, threshold_text=cls, unit="class"))
                continue
            for cert_type, label, needles in _CERTS:
                if any(re.search(n, s, re.I) for n in needles):
                    add(_spec("certificate", label, "exists", s, page.number, doc_ref,
                              threshold_text=cert_type, unit="none"))
    return out


_CERTS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("gst", "Valid GST registration", (r"\bGST(IN)?\b.*(regist|certificate|पंजीयन)", r"जीएसटी")),
    ("pan", "PAN of the bidder", (r"\bPAN\b(?!\s*India)", r"पैन")),
    ("epf", "EPF registration", (r"\bEPF\b", r"provident fund", r"भविष्य निधि")),
    ("esic", "ESIC registration", (r"\bESIC?\b",)),
    ("labour_licence", "Labour licence", (r"labou?r licen[cs]e", r"श्रम लाइसेंस")),
    ("electrical_licence", "Electrical contractor licence", (r"electrical (contractor )?licen[cs]e",)),
)


def _fmt(paise: int) -> str:
    from app.services.money import format_inr

    return format_inr(paise)


def _field(text: str, *labels: str) -> str | None:
    for label in labels:
        m = re.search(rf"{label}\s*[:：\-–]\s*(.+)", text, re.I)
        if m:
            value = m.group(1).strip().splitlines()[0].strip()
            if value:
                return value[:500]
    return None


def extract_metadata(pages: list[PageText]) -> dict[str, Any]:
    text = "\n".join(p.text for p in pages[:6])
    meta: dict[str, Any] = {}
    tid = re.search(r"\b(\d{4}_[A-Z][A-Z0-9]+_\d{3,}_\d+)\b", text)
    if tid:
        meta["tender_id"] = tid.group(1)
    ref = _field(text, r"NIT\s*No\.?", r"Tender\s*Reference\s*(?:No\.?|Number)", r"निविदा\s*क्रमांक")
    if ref:
        meta["reference_number"] = ref.split("  ")[0][:160]
    title = _field(text, r"Name\s+of\s+(?:the\s+)?Work", r"Work\s+Description", r"Title", r"कार्य\s+का\s+नाम")
    if title:
        meta["title"] = title
    dept = _field(text, r"Organi[sz]ation\s+Chain", r"Department", r"Organi[sz]ation", r"विभाग")
    if dept:
        meta["department"] = dept[:200]
    for key, labels in (
        ("estimated_value", (r"(?:Estimated|Probable)\s+(?:Amount|Cost|Value)(?:\s+of\s+(?:the\s+)?Work)?(?:\s*\(.*?\))?",
                             r"Tender\s+Value", r"अनुमानित\s+लागत")),
        ("emd", (r"EMD(?:\s+Amount)?(?:\s*\(.*?\))?", r"Earnest\s+Money(?:\s+Deposit)?", r"अमानत\s+राशि")),
        ("tender_fee", (r"Tender\s+Fee(?:\s*\(.*?\))?", r"Cost\s+of\s+(?:Tender\s+)?Document")),
    ):
        raw = _field(text, *labels)
        if raw:
            value = _amount(raw) or parse_inr(re.split(r"\s{2,}|/-", raw)[0])
            if value:
                meta[key + "_paise"] = value
    for key, labels in (
        ("bid_submission_end_at", (r"Bid\s+Submission\s+End\s+Date", r"Last\s+Date(?:\s+(?:and|&)\s+Time)?(?:\s+(?:of|for)\s+(?:online\s+)?Submission)?",
                                   r"अंतिम\s+तिथि")),
        ("bid_opening_at", (r"Bid\s+Opening\s+Date", r"Date\s+of\s+(?:Technical\s+)?Opening")),
        ("published_at", (r"Published\s+Date", r"Date\s+of\s+(?:Publication|Issue)")),
    ):
        raw = _field(text, *labels)
        if raw:
            m = _DATE.search(raw)
            if m and (dt := parse_ist_datetime(m.group(1), end_of_day=key == "bid_submission_end_at")):
                meta[key] = dt
    period = re.search(
        r"(?:period\s+of\s+completion|completion\s+period|time\s+(?:allowed|of\s+completion))[^\d]{0,40}(\d+)\s*(months?|days?|माह|दिन)",
        text, re.I,
    )
    if period:
        n = int(period.group(1))
        meta["completion_period_days"] = n * 30 if period.group(2).lower().startswith(("month", "माह")) else n
    district = find_district_in_text(text)
    if district:
        meta["district"] = district
    category, subs = classify((meta.get("title") or "") + " " + text[:3000])
    if category:
        meta["category_code"] = category
        meta["subcategory_codes"] = subs
    return meta


def extract_corrigendum_deadline(pages: list[PageText]) -> Any:
    for page in pages:
        for s in _sentences(page.text):
            if _has(s, "extend", "revised", "postpone", "बढ़ाई", "संशोधित") and _has(
                s, "date", "submission", "तिथि"
            ):
                dates = _DATE.findall(s)
                if dates:
                    return parse_ist_datetime(dates[-1], end_of_day=True), s[:400], page.number
    return None


def extract_nit(pages: list[PageText], doc_ref: str) -> ExtractedNIT:
    result = ExtractedNIT(metadata=extract_metadata(pages))
    if not any(p.text.strip() for p in pages):
        result.warnings.append(
            "No text layer found (scanned PDF?). OCR is not enabled; criteria must be entered by a reviewer."
        )
        return result
    result.requirements = extract_requirements(
        pages, doc_ref, result.metadata.get("estimated_value_paise"), result.metadata.get("category_code")
    )
    if not result.requirements:
        result.warnings.append("No eligibility criteria recognised. Review the document manually.")
    return result
