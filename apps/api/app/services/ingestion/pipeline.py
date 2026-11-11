"""Tender upsert with version tracking, cross-source dedupe and run bookkeeping."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    SourceProvider,
    SourceRun,
    Tender,
    TenderDocument,
    TenderRequirement,
    TenderVersion,
)
from app.services.ingestion.base import (
    ChangeRecord,
    NormalizedTender,
    SourceAdapter,
    SourceNotAuthorizedError,
)
from app.services.ingestion.normalize import (
    CONTENT_FIELDS,
    content_hash,
    dedupe_key,
    material_snapshot,
)
from app.services.timeutil import utcnow

log = logging.getLogger(__name__)


@dataclass
class Provenance:
    retrieval_method: str
    permission_status: str
    is_demo: bool = False
    operator_user_id: uuid.UUID | None = None
    visibility_org_id: uuid.UUID | None = None
    original_file_sha256: str | None = None
    source_run_id: uuid.UUID | None = None


@dataclass
class UpsertResult:
    tender: Tender
    outcome: str  # created | updated | unchanged | duplicate
    changed_fields: list[str] = field(default_factory=list)


def _find_canonical(db: Session, key: str, source_id: uuid.UUID, visibility_org_id: uuid.UUID | None) -> Tender | None:
    q = select(Tender).where(
        Tender.dedupe_key == key,
        Tender.source_id != source_id,
        Tender.duplicate_of_id.is_(None),
    )
    # A private import may only be linked to tenders that importer can already see.
    if visibility_org_id is None:
        q = q.where(Tender.visibility_org_id.is_(None))
    else:
        q = q.where((Tender.visibility_org_id.is_(None)) | (Tender.visibility_org_id == visibility_org_id))
    return db.scalars(q.order_by(Tender.created_at)).first()


def _apply_fields(t: Tender, nt: NormalizedTender) -> None:
    for f in CONTENT_FIELDS:
        setattr(t, f, getattr(nt, f))
    t.subcategory_codes = list(nt.subcategory_codes)
    t.source_organization = nt.source_organization


def _sync_requirements(db: Session, t: Tender, nt: NormalizedTender) -> None:
    if nt.requirements is None:
        return
    methods = {r.extraction_method for r in nt.requirements} or {"seed"}
    db.execute(
        delete(TenderRequirement).where(
            TenderRequirement.tender_id == t.id, TenderRequirement.extraction_method.in_(methods)
        )
    )
    for i, r in enumerate(nt.requirements):
        db.add(
            TenderRequirement(
                tender_id=t.id,
                requirement_type=r.requirement_type,
                label=r.label,
                mandatory=r.mandatory,
                operator=r.operator,
                threshold_value=r.threshold_value,
                threshold_text=r.threshold_text,
                unit=r.unit,
                period_years=r.period_years,
                category_code=r.category_code,
                document_ref=r.document_ref,
                page_number=r.page_number,
                clause_ref=r.clause_ref,
                evidence_quote=r.evidence_quote,
                extraction_method=r.extraction_method,
                verification_status=r.verification_status,
                sort_order=i,
            )
        )


def _sync_documents(db: Session, t: Tender, nt: NormalizedTender, prov: Provenance) -> None:
    existing = {(d.kind, d.title) for d in t.documents}
    for d in nt.documents:
        if (d.kind, d.title) in existing:
            continue
        db.add(
            TenderDocument(
                tender_id=t.id,
                kind=d.kind,
                title=d.title,
                filename=d.filename,
                source_url=d.source_url,
                is_available=d.is_available,
                retrieval_method=prov.retrieval_method,
                permission_status=prov.permission_status,
                imported_by_user_id=prov.operator_user_id,
                organization_id=prov.visibility_org_id,
            )
        )
    if nt.documents:
        t.documents_available = any(d.is_available for d in nt.documents) or t.documents_available


def upsert_tender(
    db: Session,
    source: SourceProvider,
    nt: NormalizedTender,
    prov: Provenance,
    *,
    change: ChangeRecord | None = None,
) -> UpsertResult:
    digest = content_hash(nt)
    now = utcnow()
    tender = db.scalar(
        select(Tender).where(
            Tender.source_id == source.id,
            Tender.source_tender_id == nt.source_tender_id,
            Tender.visibility_org_id.is_not_distinct_from(prov.visibility_org_id),
        )
    )

    if tender is None:
        key = dedupe_key(nt.reference_number, nt.source_tender_id)
        canonical = _find_canonical(db, key, source.id, prov.visibility_org_id)
        tender = Tender(
            source_id=source.id,
            source_tender_id=nt.source_tender_id,
            retrieval_method=prov.retrieval_method,
            permission_status=prov.permission_status,
            imported_by_user_id=prov.operator_user_id,
            imported_at=now,
            original_file_sha256=prov.original_file_sha256,
            source_run_id=prov.source_run_id,
            visibility_org_id=prov.visibility_org_id,
            is_demo=prov.is_demo,
            content_hash=digest,
            version=1,
            dedupe_key=key,
            duplicate_of_id=canonical.id if canonical else None,
            last_seen_at=now,
        )
        _apply_fields(tender, nt)
        db.add(tender)
        db.flush()
        db.add(
            TenderVersion(
                tender_id=tender.id,
                version=1,
                content_hash=digest,
                change_kind="initial",
                snapshot=material_snapshot(nt),
                source_run_id=prov.source_run_id,
            )
        )
        _sync_requirements(db, tender, nt)
        _sync_documents(db, tender, nt, prov)
        db.flush()
        db.refresh(tender)
        return UpsertResult(tender, "duplicate" if canonical else "created")

    tender.last_seen_at = now
    _sync_documents(db, tender, nt, prov)
    if tender.content_hash == digest:
        db.flush()
        return UpsertResult(tender, "unchanged")

    before = {f: getattr(tender, f) for f in CONTENT_FIELDS}
    changed = [f for f in CONTENT_FIELDS if before[f] != getattr(nt, f)]
    if nt.requirements is not None:
        current = sorted(
            (r.requirement_type, r.operator, r.mandatory, r.threshold_value, r.threshold_text, r.category_code, r.page_number)
            for r in tender.requirements
            if r.extraction_method in {s.extraction_method for s in nt.requirements}
        )
        if current != sorted(r.fingerprint() for r in nt.requirements):
            changed.append("requirements")

    if "bid_submission_end_at" in changed and before["bid_submission_end_at"] is not None:
        tender.previous_deadline_at = before["bid_submission_end_at"]
        tender.deadline_changed_at = now

    _apply_fields(tender, nt)
    tender.version += 1
    tender.content_hash = digest
    tender.source_run_id = prov.source_run_id or tender.source_run_id
    _sync_requirements(db, tender, nt)
    db.add(
        TenderVersion(
            tender_id=tender.id,
            version=tender.version,
            content_hash=digest,
            change_kind=change.kind if change else "update",
            changed_fields=changed,
            previous_values={k: _jsonable(before[k]) for k in changed if k in before},
            snapshot=material_snapshot(nt),
            corrigendum_ref=change.reference if change else None,
            note=change.note if change else None,
            source_run_id=prov.source_run_id,
        )
    )
    db.flush()
    db.refresh(tender)
    return UpsertResult(tender, "updated", changed)


def _jsonable(v: Any) -> Any:
    return v.isoformat() if isinstance(v, datetime) else v


def apply_change(nt: NormalizedTender, change: ChangeRecord) -> NormalizedTender:
    return replace(nt, **change.changes)


@dataclass
class RunCounters:
    seen: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    duplicates: int = 0
    failed: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)

    def record(self, outcome: str) -> None:
        self.seen += 1
        if outcome == "created":
            self.created += 1
        elif outcome == "updated":
            self.updated += 1
        elif outcome == "unchanged":
            self.unchanged += 1
        elif outcome == "duplicate":
            self.duplicates += 1


def start_run(
    db: Session,
    source: SourceProvider,
    *,
    trigger: str,
    slot_key: str | None = None,
    organization_id: uuid.UUID | None = None,
    operator_user_id: uuid.UUID | None = None,
    filename: str | None = None,
    file_sha256: str | None = None,
) -> SourceRun:
    run = SourceRun(
        source_id=source.id,
        trigger=trigger,
        slot_key=slot_key,
        status="running",
        organization_id=organization_id,
        operator_user_id=operator_user_id,
        filename=filename,
        file_sha256=file_sha256,
        started_at=utcnow(),
    )
    db.add(run)
    db.flush()
    return run


def finish_run(db: Session, source: SourceProvider, run: SourceRun, c: RunCounters, *, message: str | None = None) -> None:
    run.records_seen = c.seen
    run.records_created = c.created
    run.records_updated = c.updated
    run.records_unchanged = c.unchanged
    run.duplicates = c.duplicates
    run.failed_records = c.failed
    run.errors = c.errors[:200]
    run.finished_at = utcnow()
    run.message = message
    if c.failed and (c.created or c.updated or c.unchanged or c.duplicates):
        run.status = "partial"
    elif c.failed:
        run.status = "failed"
    else:
        run.status = "succeeded"
    if run.status == "failed":
        source.last_failure_at = run.finished_at
        source.last_error = (c.errors[0]["error"] if c.errors else message) or "unknown error"
    else:
        source.last_success_at = run.finished_at
    db.flush()


def run_pull_adapter(
    db: Session,
    source: SourceProvider,
    adapter: SourceAdapter,
    prov_factory: Callable[[uuid.UUID], Provenance],
    *,
    trigger: str,
    slot_key: str | None = None,
    max_attempts: int = 3,
    backoff_seconds: float = 0.0,
) -> SourceRun:
    """Run a pull-capable adapter with retries. Unauthorised sources are recorded as skipped."""
    health = adapter.health()
    if not (health.enabled and health.configured and health.authorized):
        run = start_run(db, source, trigger=trigger, slot_key=slot_key)
        run.status = "skipped"
        run.finished_at = utcnow()
        run.message = health.message
        db.flush()
        return run

    run = start_run(db, source, trigger=trigger, slot_key=slot_key)
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        run.attempt = attempt
        counters = RunCounters()
        try:
            with db.begin_nested():
                since = source.last_success_at
                prov = prov_factory(run.id)
                for sid in adapter.discover(since):
                    try:
                        with db.begin_nested():
                            _ingest_one(db, source, adapter, sid, prov, counters)
                    except Exception as exc:  # per-record failure is isolated
                        counters.failed += 1
                        counters.errors.append({"record": sid, "error": str(exc)[:300]})
            finish_run(db, source, run, counters)
            return run
        except SourceNotAuthorizedError as exc:
            run.status = "skipped"
            run.message = str(exc)
            run.finished_at = utcnow()
            db.flush()
            return run
        except Exception as exc:
            last_error = exc
            log.warning("source %s attempt %s failed: %s", source.code, attempt, exc)
            if backoff_seconds and attempt < max_attempts:
                time.sleep(backoff_seconds * 2 ** (attempt - 1))
    failed = RunCounters(failed=1, errors=[{"record": None, "error": str(last_error)[:300]}])
    finish_run(db, source, run, failed, message=f"Failed after {max_attempts} attempts")
    return run


def _ingest_one(
    db: Session,
    source: SourceProvider,
    adapter: SourceAdapter,
    sid: str,
    prov: Provenance,
    counters: RunCounters,
) -> None:
    base = adapter.fetch_metadata(sid)
    base.documents = adapter.fetch_documents(sid)
    changes = adapter.fetch_changes(sid)
    exists = db.scalar(
        select(Tender.id).where(
            Tender.source_id == source.id,
            Tender.source_tender_id == sid,
            Tender.visibility_org_id.is_not_distinct_from(prov.visibility_org_id),
        )
    )
    if exists is None and changes:
        # First sighting: replay the original record, then each corrigendum, to keep history.
        counters.record(upsert_tender(db, source, base, prov).outcome)
        current = base
        for ch in changes:
            current = apply_change(current, ch)
            upsert_tender(db, source, current, prov, change=ch)
        return
    final = base
    for ch in changes:
        final = apply_change(final, ch)
    counters.record(upsert_tender(db, source, final, prov, change=changes[-1] if changes else None).outcome)
