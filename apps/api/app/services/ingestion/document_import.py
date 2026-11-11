"""Operator-attested NIT / BOQ / corrigendum upload with deterministic extraction."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    PermissionStatus,
    SourceProvider,
    SourceRun,
    Tender,
    TenderDocument,
    TenderRequirement,
)
from app.services.extraction.ai import get_ai_extractor, grounded
from app.services.extraction.nit import PageText, extract_corrigendum_deadline, extract_nit
from app.services.extraction.readers import pdf_pages, read_boq
from app.services.ingestion.base import ChangeRecord, NormalizedTender
from app.services.ingestion.normalize import CONTENT_FIELDS, normalize_raw
from app.services.ingestion.pipeline import (
    Provenance,
    RunCounters,
    finish_run,
    start_run,
    upsert_tender,
)
from app.services.storage import get_storage, new_key
from app.services.uploads import ValidatedUpload

DOCUMENT_KINDS = ("nit", "boq", "corrigendum", "drawing", "other")


class DocumentImportError(ValueError):
    pass


@dataclass
class DocumentImportResult:
    run: SourceRun
    tender_id: uuid.UUID
    document_id: uuid.UUID
    requirements_extracted: int
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def tender_to_normalized(t: Tender) -> NormalizedTender:
    nt = NormalizedTender(source_tender_id=t.source_tender_id, title=t.title)
    for f in CONTENT_FIELDS:
        setattr(nt, f, getattr(t, f))
    nt.subcategory_codes = list(t.subcategory_codes or [])
    nt.source_organization = t.source_organization
    nt.requirements = None
    return nt


def import_document(
    db: Session,
    source: SourceProvider,
    upload: ValidatedUpload,
    *,
    kind: str,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    tender: Tender | None,
    overrides: dict[str, Any],
) -> DocumentImportResult:
    if kind not in DOCUMENT_KINDS:
        raise DocumentImportError(f"Unknown document kind '{kind}'.")
    if tender is not None and tender.visibility_org_id != organization_id:
        raise DocumentImportError(
            "Documents can only be attached to tenders your company imported. Import the tender first."
        )
    if kind == "corrigendum" and tender is None:
        raise DocumentImportError("Select the tender this corrigendum amends.")

    pages: list[PageText] = []
    metadata: dict[str, Any] = {}
    warnings: list[str] = []
    summary: dict[str, Any] = {}
    doc_ref = upload.filename

    if upload.ext == "pdf":
        try:
            pages = pdf_pages(upload.data)
        except Exception as exc:
            raise DocumentImportError(f"Could not read PDF: {exc}") from exc
    elif upload.ext == "xlsx":
        try:
            summary["boq"] = read_boq(upload.data)
        except Exception as exc:
            raise DocumentImportError(f"Could not read workbook: {exc}") from exc
    else:
        raise DocumentImportError("Tender documents must be PDF or XLSX.")

    requirements = []
    corrigendum_change: ChangeRecord | None = None
    if pages and kind in ("nit", "other"):
        extracted = extract_nit(pages, doc_ref)
        metadata, warnings = extracted.metadata, extracted.warnings
        requirements = extracted.requirements
        ai = get_ai_extractor()
        if ai is not None:
            known = {(r.requirement_type, r.threshold_value, r.threshold_text) for r in requirements}
            for r in grounded(ai.extract(pages, doc_ref), pages, doc_ref):
                if (r.requirement_type, r.threshold_value, r.threshold_text) not in known:
                    requirements.append(r)
    elif pages and kind == "corrigendum":
        found = extract_corrigendum_deadline(pages)
        if found and found[0] is not None:
            new_deadline, quote, page_no = found
            corrigendum_change = ChangeRecord(
                reference=overrides.get("corrigendum_ref") or upload.filename,
                changes={"bid_submission_end_at": new_deadline},
                note=f"p.{page_no}: {quote}",
            )
            metadata["bid_submission_end_at"] = new_deadline
        else:
            warnings.append("No revised submission date recognised; corrigendum stored for manual review.")
    summary.update(
        {
            "page_count": len(pages) or None,
            "text_available": any(p.text.strip() for p in pages),
            "metadata": {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in metadata.items()},
            "warnings": warnings,
            "requirements_extracted": len(requirements),
        }
    )

    run = start_run(
        db, source, trigger="import", organization_id=organization_id, operator_user_id=user_id,
        filename=upload.filename, file_sha256=upload.sha256,
    )
    prov = Provenance(
        retrieval_method="manual_document",
        permission_status=PermissionStatus.operator_attested,
        operator_user_id=user_id,
        visibility_org_id=organization_id,
        original_file_sha256=upload.sha256,
        source_run_id=run.id,
    )
    counters = RunCounters()

    if tender is None:
        raw: dict[str, Any] = {
            "tender_id": metadata.get("tender_id") or metadata.get("reference_number"),
            "reference_number": metadata.get("reference_number"),
            "title": metadata.get("title"),
            "department": metadata.get("department"),
            "district": metadata.get("district"),
            "category": metadata.get("category_code"),
            "estimated_value_paise": metadata.get("estimated_value_paise"),
            "emd_paise": metadata.get("emd_paise"),
            "tender_fee_paise": metadata.get("tender_fee_paise"),
            "completion_period_days": metadata.get("completion_period_days"),
            "published_at": metadata.get("published_at"),
            "bid_submission_end_at": metadata.get("bid_submission_end_at"),
            "bid_opening_at": metadata.get("bid_opening_at"),
        }
        raw.update({k: v for k, v in overrides.items() if v not in (None, "") and k != "corrigendum_ref"})
        if overrides.get("estimated_value"):
            raw.pop("estimated_value_paise", None)
        if overrides.get("deadline"):
            raw.pop("bid_submission_end_at", None)
        try:
            nt = normalize_raw(raw)
        except ValueError as exc:
            raise DocumentImportError(
                f"{exc}. Enter the missing details (Tender ID, title) in the import form."
            ) from exc
        nt.requirements = requirements
        result = upsert_tender(db, source, nt, prov)
        tender = result.tender
        counters.record(result.outcome)
    else:
        if corrigendum_change is not None:
            current = tender_to_normalized(tender)
            for k, v in corrigendum_change.changes.items():
                setattr(current, k, v)
            counters.record(upsert_tender(db, source_for(db, tender), current, prov, change=corrigendum_change).outcome)
        else:
            counters.record("unchanged")
        offset = len(tender.requirements)
        for i, r in enumerate(requirements):
            db.add(
                TenderRequirement(
                    tender_id=tender.id, requirement_type=r.requirement_type, label=r.label,
                    mandatory=r.mandatory, operator=r.operator, threshold_value=r.threshold_value,
                    threshold_text=r.threshold_text, unit=r.unit, period_years=r.period_years,
                    category_code=r.category_code or tender.category_code, document_ref=r.document_ref,
                    page_number=r.page_number, clause_ref=r.clause_ref, evidence_quote=r.evidence_quote,
                    extraction_method=r.extraction_method, verification_status=r.verification_status,
                    sort_order=offset + i,
                )
            )

    key = new_key("tender-docs", organization_id, upload.ext)
    get_storage().put(key, upload.data, upload.content_type)
    doc = TenderDocument(
        tender_id=tender.id,
        kind=kind,
        title=overrides.get("document_title") or upload.filename,
        filename=upload.filename,
        content_type=upload.content_type,
        size_bytes=upload.size,
        sha256=upload.sha256,
        storage_key=key,
        source_url=overrides.get("source_url"),
        page_count=len(pages) or None,
        is_available=True,
        extracted_summary=summary,
        retrieval_method="manual_document",
        permission_status=PermissionStatus.operator_attested,
        imported_by_user_id=user_id,
        organization_id=organization_id,
    )
    db.add(doc)
    tender.documents_available = True
    db.flush()
    db.refresh(tender)
    for r in tender.requirements:
        if r.document_id is None and r.document_ref == doc_ref and r.extraction_method != "seed":
            r.document_id = doc.id
    finish_run(db, run.source, run, counters, message=f"{len(requirements)} criteria extracted for review")
    return DocumentImportResult(run, tender.id, doc.id, len(requirements), summary["metadata"], warnings)


def source_for(db: Session, tender: Tender) -> SourceProvider:
    return db.get(SourceProvider, tender.source_id)  # type: ignore[return-value]
