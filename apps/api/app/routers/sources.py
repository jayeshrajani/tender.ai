from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select

from app.deps import DB, Admin, Analyst, Tenant, audit
from app.models import JobRun, SourceProvider, SourceRun, Tender, User
from app.services import jobs, matching
from app.services.ingestion import csv_import
from app.services.ingestion.adapters import get_adapter
from app.services.ingestion.document_import import DocumentImportError, import_document
from app.services.timeutil import (
    latest_reanalysis_slot,
    next_digest_slot,
    next_reanalysis_slot,
    slot_key,
    utcnow,
)
from app.services.uploads import UploadError, validate_upload

router = APIRouter(prefix="/api/v1", tags=["sources"])

ATTESTATION = (
    "I accessed this information on an official portal myself, completed any CAPTCHA personally, "
    "and am permitted to import it for my company's internal tender review."
)


def _collection_state(s: SourceProvider) -> str:
    """Precise wording; never 'Live' / 'Synced' / 'All tenders'."""
    if s.collection_mode == "demo_fixture":
        return "Demo data"
    if s.adapter in ("official_feed_mp", "mp_public_homepage"):
        return "Disabled – not authorised" if not s.enabled else "Authorised – pending integration"
    if s.adapter in ("manual_csv", "manual_document"):
        return "Manual import"
    return "Link only – not collected"


def _run_json(r: SourceRun, users: dict[uuid.UUID, str]) -> dict[str, Any]:
    return {
        "id": str(r.id), "source_code": r.source.code, "source_name": r.source.name, "trigger": r.trigger,
        "slot_key": r.slot_key, "status": r.status, "attempt": r.attempt, "started_at": r.started_at,
        "finished_at": r.finished_at, "records_seen": r.records_seen, "records_created": r.records_created,
        "records_updated": r.records_updated, "records_unchanged": r.records_unchanged,
        "duplicates": r.duplicates, "failed_records": r.failed_records, "errors": r.errors[:50],
        "message": r.message, "filename": r.filename, "file_sha256": r.file_sha256,
        "operator": users.get(r.operator_user_id) if r.operator_user_id else None,
    }


def _runs_query(org_id: uuid.UUID) -> Any:
    # Global scheduled runs + this company's own imports only.
    return select(SourceRun).where(
        (SourceRun.organization_id.is_(None)) | (SourceRun.organization_id == org_id)
    )


@router.get("/sources")
def list_sources(ctx: Tenant, db: DB) -> dict[str, Any]:
    sources = db.scalars(select(SourceProvider).order_by(SourceProvider.sort_order, SourceProvider.name)).all()
    counts = dict(
        db.execute(
            select(Tender.source_id, func.count())
            .where(matching.visible_tenders_clause(ctx.org_id))
            .group_by(Tender.source_id)
        ).all()
    )
    last_runs: dict[uuid.UUID, SourceRun] = {}
    for r in db.scalars(_runs_query(ctx.org_id).order_by(SourceRun.started_at.desc()).limit(300)):
        last_runs.setdefault(r.source_id, r)
    jobs_q = select(JobRun).order_by(JobRun.started_at.desc()).limit(10)
    recent_jobs = db.scalars(jobs_q).all()
    now = utcnow()
    last_slot = latest_reanalysis_slot(now)
    return {
        "schedule": {
            "timezone": "Asia/Kolkata",
            "reanalysis_times_ist": ["00:00", "08:00", "16:00"],
            "digest_time_ist": "09:00",
            "current_slot": slot_key(last_slot),
            "current_slot_ran": any(j.slot_key == slot_key(last_slot) and j.job == jobs.REANALYSIS for j in recent_jobs),
            "next_reanalysis_at": next_reanalysis_slot(now),
            "next_digest_at": next_digest_slot(now),
            "note": "Scheduled runs re-evaluate eligibility, matching and alerts. They only collect from sources that are enabled AND authorised.",
            "recent_jobs": [
                {"job": j.job, "slot_key": j.slot_key, "trigger": j.trigger, "status": j.status,
                 "started_at": j.started_at, "finished_at": j.finished_at, "stats": j.stats, "error": j.error}
                for j in recent_jobs
            ],
        },
        "items": [
            {
                "id": str(s.id), "code": s.code, "name": s.name, "owner_organization": s.owner_organization,
                "kind": s.kind, "url": s.url, "api_status": s.api_status, "collection_mode": s.collection_mode,
                "collection_state": _collection_state(s), "permission_status": s.permission_status,
                "enabled": s.enabled, "configured": s.configured, "captcha_dependency": s.captcha_dependency,
                "coverage_note": s.coverage_note, "phase": s.phase, "priority": s.priority,
                "health_message": (a.health().message if (a := get_adapter(s)) else "Not collected by TenderOS."),
                "last_success_at": s.last_success_at, "last_failure_at": s.last_failure_at,
                "last_error": s.last_error, "tender_count": counts.get(s.id, 0),
                "last_run": (
                    {"status": lr.status, "started_at": lr.started_at, "message": lr.message}
                    if (lr := last_runs.get(s.id)) else None
                ),
                "supports_import": s.collection_mode in ("manual_csv_import", "manual_document_import")
                or s.adapter in ("manual_csv", "manual_document"),
            }
            for s in sources
        ],
        "attestation_text": ATTESTATION,
    }


@router.get("/ingestion/runs")
def list_runs(
    ctx: Tenant, db: DB, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)
) -> dict[str, Any]:
    q = _runs_query(ctx.org_id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    runs = db.scalars(q.order_by(SourceRun.started_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    ids = {r.operator_user_id for r in runs if r.operator_user_id}
    users = dict(db.execute(select(User.id, User.full_name).where(User.id.in_(ids))).all()) if ids else {}
    return {"items": [_run_json(r, users) for r in runs], "total": total, "page": page, "page_size": page_size}


@router.post("/ingestion/csv/preview")
async def csv_preview(ctx: Analyst, file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read()
    try:
        validate_upload(file.filename, data, {"csv"})
        return csv_import.preview(data)
    except (UploadError, csv_import.CSVImportError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.post("/ingestion/import", status_code=201)
async def ingestion_import(
    ctx: Analyst,
    db: DB,
    file: UploadFile = File(...),
    kind: str = Form(...),  # csv | nit | boq | corrigendum | other
    attestation: bool = Form(False),
    mapping: str | None = Form(default=None),
    source_portal_url: str | None = Form(default=None),
    source_organization: str | None = Form(default=None),
    tender_id: str | None = Form(default=None),
    title: str | None = Form(default=None),
    source_tender_id: str | None = Form(default=None),
    reference_number: str | None = Form(default=None),
    department: str | None = Form(default=None),
    district: str | None = Form(default=None),
    estimated_value: str | None = Form(default=None),
    deadline: str | None = Form(default=None),
    corrigendum_ref: str | None = Form(default=None),
) -> dict[str, Any]:
    if not attestation:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Confirm the import attestation to continue.")
    if source_portal_url and not source_portal_url.lower().startswith(("https://", "http://")):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Source URL must be an http(s) link.")
    data = await file.read()
    try:
        if kind == "csv":
            up = validate_upload(file.filename, data, {"csv"})
            source = db.scalar(select(SourceProvider).where(SourceProvider.code == "manual_csv"))
            assert source is not None
            try:
                parsed_mapping = json.loads(mapping) if mapping else None
            except json.JSONDecodeError as exc:
                raise csv_import.CSVImportError("Column mapping is not valid JSON.") from exc
            if parsed_mapping is None:
                headers, _ = csv_import.read_rows(up.data)
                parsed_mapping = csv_import.suggest_mapping(headers)
            if not isinstance(parsed_mapping, dict):
                raise csv_import.CSVImportError("Column mapping must be an object.")
            run = csv_import.import_csv(
                db, source,
                csv_import.CSVImportRequest(
                    data=up.data, filename=up.filename, sha256=up.sha256,
                    mapping={str(k): (str(v) if v else None) for k, v in parsed_mapping.items() if k in csv_import.TARGET_FIELDS},
                    source_portal_url=source_portal_url, source_organization=source_organization,
                ),
                organization_id=ctx.org_id, user_id=ctx.user.id,
            )
            audit(db, ctx, "import.csv", "source_run", run.id, {"file": up.filename, "status": run.status})
            matching.recompute_for_org(db, ctx.org_id)
            db.commit()
            return {"run": _run_json(run, {ctx.user.id: ctx.user.full_name})}

        up = validate_upload(file.filename, data, {"pdf", "xlsx"})
        source = db.scalar(select(SourceProvider).where(SourceProvider.code == "manual_document"))
        assert source is not None
        target = None
        if tender_id:
            try:
                tid = uuid.UUID(tender_id)
            except ValueError as exc:
                raise DocumentImportError("Invalid tender id") from exc
            target = db.scalar(select(Tender).where(Tender.id == tid, matching.visible_tenders_clause(ctx.org_id)))
            if target is None:
                raise DocumentImportError("Tender not found")
        overrides = {
            "title": title, "tender_id": source_tender_id, "reference_number": reference_number,
            "department": department, "district": district, "estimated_value": estimated_value,
            "deadline": deadline, "source_url": source_portal_url,
            "source_organization": source_organization, "corrigendum_ref": corrigendum_ref,
        }
        result = import_document(
            db, source, up, kind=kind, organization_id=ctx.org_id, user_id=ctx.user.id,
            tender=target, overrides=overrides,
        )
        audit(db, ctx, f"import.{kind}", "tender", result.tender_id, {"file": up.filename})
        matching.recompute_for_org(db, ctx.org_id)
        db.commit()
        return {
            "run": _run_json(result.run, {ctx.user.id: ctx.user.full_name}),
            "tender_id": str(result.tender_id),
            "document_id": str(result.document_id),
            "requirements_extracted": result.requirements_extracted,
            "metadata": result.metadata,
            "warnings": result.warnings,
        }
    except (UploadError, csv_import.CSVImportError, DocumentImportError) as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.post("/ingestion/run", status_code=202)
def trigger_run(ctx: Admin, db: DB) -> dict[str, Any]:
    """Manually run the reanalysis job now (same code path as the 8-hourly schedule)."""
    key = f"manual-{utcnow():%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
    audit(db, ctx, "ingestion.manual_run", "job_run", key)
    db.commit()
    job = jobs.run_reanalysis(db, key, trigger="manual")
    if job is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A run for this slot already exists")
    return {"job": job.job, "slot_key": job.slot_key, "status": job.status, "stats": job.stats, "error": job.error}
