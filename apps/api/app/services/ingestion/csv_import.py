"""Operator-attested CSV import with column mapping, validation and duplicate detection."""

from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models import PermissionStatus, SourceProvider, SourceRun
from app.services.ingestion.normalize import normalize_raw
from app.services.ingestion.pipeline import (
    Provenance,
    RunCounters,
    finish_run,
    start_run,
    upsert_tender,
)

MAX_ROWS = 5000

# target field → (label, required, header synonyms)
TARGET_FIELDS: dict[str, tuple[str, bool, tuple[str, ...]]] = {
    "tender_id": ("Tender ID", True, ("tender id", "tender_id", "tenderid", "निविदा आईडी", "e-published tender id")),
    "title": ("Title / name of work", True, ("title", "name of work", "work name", "tender title", "work description", "कार्य का नाम")),
    "reference_number": ("Reference / NIT no.", False, ("reference no", "reference number", "ref no", "nit no", "tender reference", "निविदा क्रमांक")),
    "department": ("Department", False, ("department", "dept", "विभाग")),
    "issuing_organization": ("Issuing organisation", False, ("organisation", "organization", "organisation chain", "organization chain", "issuing authority")),
    "district": ("District", False, ("district", "जिला", "location district")),
    "location": ("Location", False, ("location", "work location", "स्थान")),
    "category": ("Work category", False, ("category", "work category", "product category", "tender category")),
    "estimated_value": ("Estimated value (₹)", False, ("estimated value", "estimated cost", "tender value", "value", "amount", "अनुमानित लागत")),
    "emd": ("EMD (₹)", False, ("emd", "emd amount", "earnest money")),
    "tender_fee": ("Tender fee (₹)", False, ("tender fee", "document fee")),
    "published_at": ("Published date", False, ("published date", "e-published date", "publish date")),
    "bid_submission_end_at": ("Submission deadline (IST)", False, ("bid submission end date", "closing date", "last date", "submission end date", "deadline", "अंतिम तिथि")),
    "bid_opening_at": ("Bid opening date", False, ("bid opening date", "opening date")),
    "completion_period": ("Completion period", False, ("period of work", "completion period", "time allowed")),
    "source_url": ("Official tender URL", False, ("url", "link", "tender url", "source url")),
}


class CSVImportError(ValueError):
    pass


def _norm(h: str) -> str:
    return re.sub(r"[\s_\-.()]+", " ", h.strip().lower()).strip()


def decode_csv(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise CSVImportError("CSV must be UTF-8 encoded.")


def read_rows(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    text = decode_csv(data)
    reader = csv.DictReader(io.StringIO(text))
    headers = [h for h in (reader.fieldnames or []) if h is not None]
    if not headers:
        raise CSVImportError("CSV has no header row.")
    rows: list[dict[str, str]] = []
    for i, row in enumerate(reader):
        if i >= MAX_ROWS:
            raise CSVImportError(f"CSV exceeds {MAX_ROWS} rows; split the file.")
        rows.append({k: (v or "") for k, v in row.items() if k is not None})
    return headers, rows


def suggest_mapping(headers: list[str]) -> dict[str, str | None]:
    normalized = {_norm(h): h for h in headers}
    mapping: dict[str, str | None] = {}
    for field, (_, _, synonyms) in TARGET_FIELDS.items():
        mapping[field] = next((normalized[_norm(s)] for s in synonyms if _norm(s) in normalized), None)
    return mapping


def preview(data: bytes) -> dict[str, Any]:
    headers, rows = read_rows(data)
    return {
        "headers": headers,
        "row_count": len(rows),
        "sample": rows[:5],
        "suggested_mapping": suggest_mapping(headers),
        "fields": [
            {"key": k, "label": label, "required": req} for k, (label, req, _) in TARGET_FIELDS.items()
        ],
    }


@dataclass
class CSVImportRequest:
    data: bytes
    filename: str
    sha256: str
    mapping: dict[str, str | None]
    source_portal_url: str | None
    source_organization: str | None


def import_csv(
    db: Session,
    source: SourceProvider,
    req: CSVImportRequest,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
) -> SourceRun:
    headers, rows = read_rows(req.data)
    for field, (label, required, _) in TARGET_FIELDS.items():
        col = req.mapping.get(field)
        if required and not col:
            raise CSVImportError(f"Map a column to '{label}'.")
        if col and col not in headers:
            raise CSVImportError(f"Column '{col}' is not in the file.")

    run = start_run(
        db, source, trigger="import", organization_id=organization_id, operator_user_id=user_id,
        filename=req.filename, file_sha256=req.sha256,
    )
    prov = Provenance(
        retrieval_method="manual_csv",
        permission_status=PermissionStatus.operator_attested,
        operator_user_id=user_id,
        visibility_org_id=organization_id,
        original_file_sha256=req.sha256,
        source_run_id=run.id,
    )
    counters = RunCounters()
    seen_in_file: set[str] = set()
    for idx, row in enumerate(rows, start=2):  # header is line 1
        raw = {field: row.get(col, "") for field, col in req.mapping.items() if col}
        if not raw.get("source_url"):
            raw["source_url"] = req.source_portal_url
        raw["source_organization"] = req.source_organization
        tid = (raw.get("tender_id") or "").strip()
        if tid and tid in seen_in_file:
            counters.seen += 1
            counters.duplicates += 1
            counters.errors.append({"row": idx, "error": f"Duplicate tender ID '{tid}' in file; row skipped."})
            continue
        try:
            with db.begin_nested():
                nt = normalize_raw(raw)
                seen_in_file.add(nt.source_tender_id)
                counters.record(upsert_tender(db, source, nt, prov).outcome)
        except ValueError as exc:
            counters.seen += 1
            counters.failed += 1
            counters.errors.append({"row": idx, "error": str(exc)})
    finish_run(db, source, run, counters)
    return run
