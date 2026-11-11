"""Normalisation of raw tender fields into ``NormalizedTender``."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import datetime
from typing import Any

from app.services.districts import find_district_in_text, normalize_district
from app.services.ingestion.base import NormalizedTender
from app.services.money import parse_inr
from app.services.taxonomy import CATEGORY_CODES, classify
from app.services.timeutil import parse_ist_datetime

# Fields that make up a tender's material content (used for hashing + version diffs).
CONTENT_FIELDS = (
    "title",
    "reference_number",
    "department",
    "issuing_organization",
    "district",
    "location",
    "category_code",
    "tender_type",
    "estimated_value_paise",
    "emd_paise",
    "tender_fee_paise",
    "completion_period_days",
    "published_at",
    "bid_submission_start_at",
    "bid_submission_end_at",
    "bid_opening_at",
    "pre_bid_meeting_at",
    "status",
    "nit_summary",
    "source_url",
)


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def dedupe_key(reference_number: str | None, source_tender_id: str) -> str:
    """Cross-source identity: the portal tender ID / NIT reference, alphanumerics only."""
    base = reference_number or source_tender_id
    return re.sub(r"[^A-Z0-9]", "", base.upper())


def _parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    m = re.search(r"\d+", str(value))
    return int(m.group()) if m else None


def _days(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    n = _parse_int(text)
    if n is None:
        return None
    lowered = text.lower()
    if "month" in lowered or "माह" in lowered:
        return n * 30
    if "year" in lowered or "वर्ष" in lowered:
        return n * 365
    return n


def normalize_raw(raw: dict[str, Any]) -> NormalizedTender:
    """Normalise a flat dict (CSV row / extracted metadata). Raises ValueError on missing essentials."""
    title = clean_text(raw.get("title"))
    source_tender_id = clean_text(raw.get("source_tender_id") or raw.get("tender_id"))
    if not title:
        raise ValueError("title is required")
    if not source_tender_id:
        raise ValueError("tender_id is required")

    district = normalize_district(clean_text(raw.get("district")))
    if district is None:
        district = find_district_in_text(" ".join(filter(None, [title, clean_text(raw.get("location"))])))

    category = clean_text(raw.get("category"))
    category_code = category.lower().replace(" ", "_") if category else None
    subs: list[str] = []
    if category_code not in CATEGORY_CODES:
        category_code, subs = classify(title + " " + (clean_text(raw.get("nit_summary")) or ""))
    else:
        _, subs = classify(title)

    deadline_raw = raw.get("bid_submission_end_at") or raw.get("deadline")
    deadline = _as_dt(deadline_raw, end_of_day=True)
    if raw.get("bid_submission_end_at") or raw.get("deadline"):
        if deadline is None:
            raise ValueError(f"could not parse submission deadline '{deadline_raw}'")

    estimated_raw = raw.get("estimated_value") or raw.get("estimated_value_paise")
    estimated = (
        raw["estimated_value_paise"]
        if isinstance(raw.get("estimated_value_paise"), int)
        else parse_inr(estimated_raw)
    )
    if estimated_raw not in (None, "") and estimated is None:
        raise ValueError(f"could not parse estimated value '{estimated_raw}'")

    source_url = clean_text(raw.get("source_url"))
    if source_url and not re.match(r"^https?://", source_url, re.I):
        raise ValueError("source URL must start with http:// or https://")

    return NormalizedTender(
        source_tender_id=source_tender_id,
        title=title,
        reference_number=clean_text(raw.get("reference_number")),
        department=clean_text(raw.get("department")),
        issuing_organization=clean_text(raw.get("issuing_organization") or raw.get("organisation")),
        district=district,
        location=clean_text(raw.get("location")),
        category_code=category_code,
        subcategory_codes=subs,
        tender_type=clean_text(raw.get("tender_type")),
        estimated_value_paise=estimated,
        emd_paise=raw["emd_paise"] if isinstance(raw.get("emd_paise"), int) else parse_inr(raw.get("emd")),
        tender_fee_paise=(
            raw["tender_fee_paise"]
            if isinstance(raw.get("tender_fee_paise"), int)
            else parse_inr(raw.get("tender_fee"))
        ),
        completion_period_days=_days(raw.get("completion_period") or raw.get("completion_period_days")),
        published_at=_as_dt(raw.get("published_at")),
        bid_submission_start_at=_as_dt(raw.get("bid_submission_start_at")),
        bid_submission_end_at=deadline,
        bid_opening_at=_as_dt(raw.get("bid_opening_at")),
        pre_bid_meeting_at=_as_dt(raw.get("pre_bid_meeting_at")),
        status=clean_text(raw.get("status")) or "active",
        nit_summary=clean_text(raw.get("nit_summary")),
        source_url=source_url,
        source_organization=clean_text(raw.get("source_organization")),
    )


def _as_dt(value: Any, *, end_of_day: bool = False) -> datetime | None:
    if isinstance(value, datetime):
        return value
    return parse_ist_datetime(clean_text(value), end_of_day=end_of_day)


def material_snapshot(nt: NormalizedTender) -> dict[str, Any]:
    snap = {f: getattr(nt, f) for f in CONTENT_FIELDS}
    snap["subcategory_codes"] = sorted(nt.subcategory_codes)
    snap["requirements"] = (
        sorted(json.dumps(r.fingerprint(), default=str) for r in nt.requirements)
        if nt.requirements is not None
        else None
    )
    return json.loads(json.dumps(snap, default=_json_default))


def content_hash(nt: NormalizedTender) -> str:
    return hashlib.sha256(
        json.dumps(material_snapshot(nt), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _json_default(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


def to_dict(nt: NormalizedTender) -> dict[str, Any]:
    return json.loads(json.dumps(asdict(nt), default=_json_default))
