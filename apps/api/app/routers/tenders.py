from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session

from app.deps import DB, Analyst, Tenant, TenantContext, audit
from app.models import (
    CompanyRequirementEvaluation,
    CompanyTenderMatch,
    EligibilityStatus,
    ReviewNote,
    SavedTender,
    SavedView,
    SourceProvider,
    Tender,
    TenderRequirement,
    TenderVersion,
    User,
)
from app.schemas import NoteIn, RequirementReviewIn, SavedViewIn, SaveTenderIn
from app.services import matching
from app.services.matching import visible_tenders_clause
from app.services.storage import sign_download
from app.services.timeutil import utcnow

router = APIRouter(prefix="/api/v1", tags=["tenders"])

SORTS = {
    "relevance": CompanyTenderMatch.relevance_score,
    "deadline": Tender.bid_submission_end_at,
    "value": Tender.estimated_value_paise,
    "published": Tender.published_at,
    "title": Tender.title,
}


def ensure_matches(db: Session, org_id: uuid.UUID) -> None:
    missing = db.scalar(
        select(func.count())
        .select_from(Tender)
        .where(
            visible_tenders_clause(org_id),
            Tender.duplicate_of_id.is_(None),
            ~exists().where(
                CompanyTenderMatch.tender_id == Tender.id, CompanyTenderMatch.organization_id == org_id
            ),
        )
    )
    if missing:
        matching.recompute_for_org(db, org_id)
        db.commit()


def _action_expr(now: Any) -> Any:
    return case(
        (or_(Tender.status != "active", Tender.bid_submission_end_at < now), "closed"),
        (SavedTender.state == "dismissed", "dismissed"),
        (CompanyTenderMatch.eligibility_status == EligibilityStatus.NOT_ELIGIBLE, "not_eligible"),
        (CompanyTenderMatch.eligibility_status == EligibilityStatus.NEEDS_VERIFICATION, "verify"),
        else_="review",
    )


def _joined(stmt: Any, org_id: uuid.UUID) -> Any:
    return (
        stmt.join(
            CompanyTenderMatch,
            and_(CompanyTenderMatch.tender_id == Tender.id, CompanyTenderMatch.organization_id == org_id),
        )
        .outerjoin(SavedTender, and_(SavedTender.tender_id == Tender.id, SavedTender.organization_id == org_id))
        .where(visible_tenders_clause(org_id), Tender.duplicate_of_id.is_(None))
    )


def _base_query(org_id: uuid.UUID, now: Any) -> Any:
    action = _action_expr(now).label("action")
    stmt = select(Tender, CompanyTenderMatch, SavedTender.state.label("saved_state"), action).select_from(Tender)
    return _joined(stmt, org_id), action


def tender_row(t: Tender, m: CompanyTenderMatch, saved_state: str | None, action: str) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "title": t.title,
        "reference_number": t.reference_number,
        "department": t.department,
        "issuing_organization": t.issuing_organization,
        "district": t.district,
        "category_code": t.category_code,
        "estimated_value_paise": t.estimated_value_paise,
        "published_at": t.published_at,
        "deadline": t.bid_submission_end_at,
        "previous_deadline": t.previous_deadline_at,
        "deadline_changed_at": t.deadline_changed_at,
        "status": t.status,
        "is_demo": t.is_demo,
        "retrieval_method": t.retrieval_method,
        "documents_available": t.documents_available,
        "eligibility_status": m.eligibility_status,
        "eligibility_summary": m.eligibility_summary,
        "mandatory_failures": m.mandatory_failures,
        "unknown_count": m.unknown_count,
        "relevance_score": float(m.relevance_score),
        "saved_state": saved_state,
        "action": action,
    }


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/tenders")
def list_tenders(
    ctx: Tenant,
    db: DB,
    q: str | None = Query(default=None, max_length=200),
    district: list[str] = Query(default=[]),
    category: list[str] = Query(default=[]),
    eligibility: list[str] = Query(default=[]),
    action: list[str] = Query(default=[]),
    min_value: int | None = Query(default=None, ge=0),
    max_value: int | None = Query(default=None, ge=0),
    closing_within: int | None = Query(default=None, ge=0, le=365),
    changed_within: int | None = Query(default=None, ge=1, le=90),
    min_score: float | None = Query(default=None, ge=0, le=100),
    saved: bool = False,
    include_closed: bool = False,
    sort: Literal["relevance", "deadline", "value", "published", "title"] = "relevance",
    order: Literal["asc", "desc"] | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> dict[str, Any]:
    ensure_matches(db, ctx.org_id)
    now = utcnow()
    query, _ = _base_query(ctx.org_id, now)
    action_expr = _action_expr(now)
    conds: list[Any] = []
    if q and q.strip():
        like = f"%{_escape_like(q.strip())}%"
        conds.append(
            or_(
                Tender.title.ilike(like, escape="\\"),
                Tender.reference_number.ilike(like, escape="\\"),
                Tender.department.ilike(like, escape="\\"),
                Tender.issuing_organization.ilike(like, escape="\\"),
                Tender.location.ilike(like, escape="\\"),
                Tender.district.ilike(like, escape="\\"),
            )
        )
    if district:
        conds.append(Tender.district.in_(district))
    if category:
        conds.append(Tender.category_code.in_(category))
    if eligibility:
        conds.append(CompanyTenderMatch.eligibility_status.in_(eligibility))
    if min_value is not None:
        conds.append(Tender.estimated_value_paise >= min_value)
    if max_value is not None:
        conds.append(Tender.estimated_value_paise <= max_value)
    if closing_within is not None:
        conds.append(Tender.bid_submission_end_at >= now)
        conds.append(Tender.bid_submission_end_at <= now + timedelta(days=closing_within))
    if min_score is not None:
        conds.append(CompanyTenderMatch.relevance_score >= min_score)
    if changed_within is not None:
        conds.append(Tender.deadline_changed_at >= now - timedelta(days=changed_within))
    if saved:
        conds.append(SavedTender.state == "saved")
    if action:
        conds.append(action_expr.in_(action))
    elif not include_closed:
        conds.append(action_expr.not_in(["closed", "dismissed"]))

    count_stmt = _joined(select(func.count()).select_from(Tender), ctx.org_id).where(*conds)
    total = db.scalar(count_stmt) or 0
    col = SORTS[sort]
    direction = order or ("desc" if sort in ("relevance", "value", "published") else "asc")
    ordered = col.desc().nulls_last() if direction == "desc" else col.asc().nulls_last()
    rows = db.execute(
        query.where(*conds).order_by(ordered, Tender.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [tender_row(t, m, s, a) for t, m, s, a in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "sort": sort,
        "order": direction,
        "generated_at": now,
    }


@router.get("/tenders/facets")
def facets(ctx: Tenant, db: DB) -> dict[str, Any]:
    ensure_matches(db, ctx.org_id)
    base = and_(visible_tenders_clause(ctx.org_id), Tender.duplicate_of_id.is_(None))
    districts = db.execute(
        select(Tender.district, func.count()).where(base, Tender.district.is_not(None))
        .group_by(Tender.district).order_by(Tender.district)
    ).all()
    categories = db.execute(
        select(Tender.category_code, func.count()).where(base, Tender.category_code.is_not(None))
        .group_by(Tender.category_code)
    ).all()
    return {
        "districts": [{"value": d, "count": c} for d, c in districts],
        "categories": [{"value": d, "count": c} for d, c in categories],
    }


@router.get("/dashboard")
def dashboard(ctx: Tenant, db: DB) -> dict[str, Any]:
    ensure_matches(db, ctx.org_id)
    now = utcnow()
    sub = _joined(
        select(
            Tender.bid_submission_end_at.label("deadline"),
            Tender.deadline_changed_at,
            CompanyTenderMatch.relevance_score,
            _action_expr(now).label("action"),
        ).select_from(Tender),
        ctx.org_id,
    ).subquery()
    open_ = sub.c.action.not_in(["closed", "dismissed"])

    def count(*conds: Any) -> int:
        return db.scalar(select(func.count()).select_from(sub).where(open_, *conds)) or 0

    worth = count(sub.c.action.in_(["review", "verify"]), sub.c.relevance_score >= 50)
    closing = count(
        sub.c.deadline <= now + timedelta(days=7), sub.c.action.in_(["review", "verify"])
    )
    verify = count(sub.c.action == "verify")
    changed = count(sub.c.deadline_changed_at >= now - timedelta(days=7))
    gaps = db.execute(
        select(TenderRequirement.requirement_type, TenderRequirement.threshold_text, func.count())
        .join(CompanyRequirementEvaluation, CompanyRequirementEvaluation.requirement_id == TenderRequirement.id)
        .join(Tender, Tender.id == TenderRequirement.tender_id)
        .where(
            CompanyRequirementEvaluation.organization_id == ctx.org_id,
            CompanyRequirementEvaluation.result == "UNKNOWN",
            TenderRequirement.mandatory.is_(True),
            Tender.status == "active",
            Tender.bid_submission_end_at > now,
        )
        .group_by(TenderRequirement.requirement_type, TenderRequirement.threshold_text)
        .order_by(func.count().desc())
        .limit(5)
    ).all()
    return {
        "counts": {
            "worth_reviewing": worth,
            "closing_7d": closing,
            "needs_verification": verify,
            "deadline_changed_7d": changed,
        },
        "evidence_gaps": [
            {"requirement_type": rt, "detail": tt, "tenders": n} for rt, tt, n in gaps
        ],
        "generated_at": now,
    }


def get_visible_tender(db: Session, ctx: TenantContext, tender_id: uuid.UUID) -> Tender:
    t = db.scalar(select(Tender).where(Tender.id == tender_id, visible_tenders_clause(ctx.org_id)))
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tender not found")
    return t


def _match(db: Session, ctx: TenantContext, t: Tender) -> CompanyTenderMatch:
    m = db.scalar(
        select(CompanyTenderMatch).where(
            CompanyTenderMatch.organization_id == ctx.org_id, CompanyTenderMatch.tender_id == t.id
        )
    )
    if m is None or m.tender_version != t.version:
        m, _ = matching.compute_match(db, ctx.org_id, t)
        db.commit()
    return m


def _eligibility_payload(db: Session, ctx: TenantContext, t: Tender, m: CompanyTenderMatch) -> dict[str, Any]:
    evals = {
        e.requirement_id: e
        for e in db.scalars(
            select(CompanyRequirementEvaluation).where(
                CompanyRequirementEvaluation.match_id == m.id,
                CompanyRequirementEvaluation.organization_id == ctx.org_id,
            )
        )
    }
    docs = {d.id: d for d in t.documents}
    rows = []
    for r in t.requirements:
        e = evals.get(r.id)
        doc = docs.get(r.document_id) if r.document_id else None
        rows.append(
            {
                "id": str(r.id),
                "requirement_type": r.requirement_type,
                "label": r.label,
                "mandatory": r.mandatory,
                "operator": r.operator,
                "threshold_value": r.threshold_value,
                "threshold_text": r.threshold_text,
                "unit": r.unit,
                "period_years": r.period_years,
                "citation": {
                    "document": doc.title if doc else r.document_ref,
                    "document_id": str(doc.id) if doc else None,
                    "page": r.page_number,
                    "clause": r.clause_ref,
                    "quote": r.evidence_quote,
                },
                "extraction_method": r.extraction_method,
                "verification_status": r.verification_status,
                "result": e.result if e else ("NOT_APPLICABLE" if r.verification_status == "rejected" else "UNKNOWN"),
                "explanation": e.explanation if e else "Criterion rejected by reviewer; excluded from evaluation."
                if r.verification_status == "rejected" else "Not evaluated yet.",
                "company_evidence": e.company_evidence if e else [],
            }
        )
    return {
        "status": m.eligibility_status,
        "summary": m.eligibility_summary,
        "mandatory_failures": m.mandatory_failures,
        "unknown_count": m.unknown_count,
        "computed_at": m.computed_at,
        "requirements": rows,
        "disclaimer": "Indicative check against your recorded profile. It does not guarantee acceptance by the procuring authority.",
    }


def _documents_payload(db: Session, ctx: TenantContext, t: Tender) -> list[dict[str, Any]]:
    out = []
    for d in t.documents:
        # Private document files are only visible to the company that uploaded them.
        if d.organization_id is not None and d.organization_id != ctx.org_id:
            continue
        out.append(
            {
                "id": str(d.id), "kind": d.kind, "title": d.title, "filename": d.filename,
                "size_bytes": d.size_bytes, "page_count": d.page_count, "is_available": d.is_available,
                "source_url": d.source_url, "sha256": d.sha256, "retrieval_method": d.retrieval_method,
                "permission_status": d.permission_status, "created_at": d.created_at,
                "extracted_summary": d.extracted_summary,
            }
        )
    return out


@router.get("/tenders/{tender_id}")
def get_tender(tender_id: uuid.UUID, ctx: Tenant, db: DB) -> dict[str, Any]:
    t = get_visible_tender(db, ctx, tender_id)
    m = _match(db, ctx, t)
    saved = db.scalar(
        select(SavedTender.state).where(SavedTender.organization_id == ctx.org_id, SavedTender.tender_id == t.id)
    )
    now = utcnow()
    action = (
        "closed" if t.status != "active" or (t.bid_submission_end_at and t.bid_submission_end_at < now)
        else "dismissed" if saved == "dismissed"
        else {"NOT_ELIGIBLE": "not_eligible", "NEEDS_VERIFICATION": "verify"}.get(m.eligibility_status, "review")
    )
    versions = db.scalars(
        select(TenderVersion).where(TenderVersion.tender_id == t.id).order_by(TenderVersion.version)
    ).all()
    importer = db.get(User, t.imported_by_user_id) if t.imported_by_user_id else None
    canonical_id = t.duplicate_of_id or t.id
    related = db.execute(
        select(Tender.id, SourceProvider.name, Tender.retrieval_method, Tender.imported_at)
        .join(SourceProvider, SourceProvider.id == Tender.source_id)
        .where(
            or_(Tender.duplicate_of_id == canonical_id, Tender.id == canonical_id),
            Tender.id != t.id,
            visible_tenders_clause(ctx.org_id),
        )
    ).all()
    notes = db.scalars(
        select(ReviewNote).where(ReviewNote.organization_id == ctx.org_id, ReviewNote.tender_id == t.id)
        .order_by(ReviewNote.created_at.desc())
    ).all()

    timeline: list[dict[str, Any]] = [
        {"at": t.published_at, "kind": "published", "label": "Published"},
        {"at": t.bid_submission_start_at, "kind": "bid_start", "label": "Bid submission opens"},
        {"at": t.pre_bid_meeting_at, "kind": "pre_bid", "label": "Pre-bid meeting"},
        *[
            {"at": v.captured_at, "kind": v.change_kind, "label": f"{v.corrigendum_ref or 'Update'}: {', '.join(v.changed_fields)}",
             "note": v.note}
            for v in versions if v.version > 1
        ],
        {"at": t.bid_submission_end_at, "kind": "deadline", "label": "Bid submission closes"},
        {"at": t.bid_opening_at, "kind": "opening", "label": "Technical bid opening"},
    ]
    return {
        **tender_row(t, m, saved, action),
        "source_tender_id": t.source_tender_id,
        "location": t.location,
        "subcategory_codes": t.subcategory_codes,
        "tender_type": t.tender_type,
        "emd_paise": t.emd_paise,
        "tender_fee_paise": t.tender_fee_paise,
        "completion_period_days": t.completion_period_days,
        "bid_submission_start_at": t.bid_submission_start_at,
        "bid_opening_at": t.bid_opening_at,
        "pre_bid_meeting_at": t.pre_bid_meeting_at,
        "nit_summary": t.nit_summary,
        "version": t.version,
        "provenance": {
            "source_name": t.source.name,
            "source_code": t.source.code,
            "source_url": t.source_url,
            "source_organization": t.source_organization,
            "retrieval_method": t.retrieval_method,
            "permission_status": t.permission_status,
            "imported_at": t.imported_at,
            "imported_by": importer.full_name if importer else None,
            "original_file_sha256": t.original_file_sha256,
            "last_seen_at": t.last_seen_at,
            "is_private_import": t.visibility_org_id is not None,
        },
        "also_seen_in": [
            {"tender_id": str(i), "source": n, "retrieval_method": rm, "imported_at": ia} for i, n, rm, ia in related
        ],
        "documents": _documents_payload(db, ctx, t),
        "versions": [
            {"version": v.version, "change_kind": v.change_kind, "changed_fields": v.changed_fields,
             "previous_values": v.previous_values, "corrigendum_ref": v.corrigendum_ref, "note": v.note,
             "captured_at": v.captured_at}
            for v in versions
        ],
        "timeline": sorted((e for e in timeline if e["at"]), key=lambda e: e["at"]),
        "eligibility": _eligibility_payload(db, ctx, t, m),
        "relevance": {"score": float(m.relevance_score), "breakdown": m.score_breakdown},
        "notes": [
            {"id": str(n.id), "body": n.body, "author": n.author.full_name if n.author else "Former member",
             "created_at": n.created_at}
            for n in notes
        ],
        "can_review_requirements": t.visibility_org_id == ctx.org_id and ctx.role != "viewer",
    }


@router.get("/tenders/{tender_id}/documents")
def tender_documents(tender_id: uuid.UUID, ctx: Tenant, db: DB) -> dict[str, Any]:
    t = get_visible_tender(db, ctx, tender_id)
    return {"items": _documents_payload(db, ctx, t)}


@router.get("/tenders/{tender_id}/documents/{doc_id}/link")
def tender_document_link(tender_id: uuid.UUID, doc_id: uuid.UUID, ctx: Tenant, db: DB) -> dict[str, str]:
    t = get_visible_tender(db, ctx, tender_id)
    doc = next((d for d in t.documents if d.id == doc_id), None)
    if doc is None or not doc.storage_key or (doc.organization_id not in (None, ctx.org_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document file not available")
    token = sign_download(doc.storage_key, ctx.org_id, doc.filename or "document", doc.content_type or "application/octet-stream")
    return {"url": f"/api/v1/files/{token}"}


@router.get("/tenders/{tender_id}/eligibility")
def tender_eligibility(tender_id: uuid.UUID, ctx: Tenant, db: DB) -> dict[str, Any]:
    t = get_visible_tender(db, ctx, tender_id)
    return _eligibility_payload(db, ctx, t, _match(db, ctx, t))


@router.get("/tenders/{tender_id}/match")
def tender_match(tender_id: uuid.UUID, ctx: Tenant, db: DB) -> dict[str, Any]:
    t = get_visible_tender(db, ctx, tender_id)
    m = _match(db, ctx, t)
    return {
        "eligibility_status": m.eligibility_status,
        "eligibility_summary": m.eligibility_summary,
        "relevance_score": float(m.relevance_score),
        "breakdown": m.score_breakdown,
        "computed_at": m.computed_at,
    }


@router.post("/tenders/{tender_id}/save")
def save_tender(tender_id: uuid.UUID, body: SaveTenderIn, ctx: Analyst, db: DB) -> dict[str, Any]:
    t = get_visible_tender(db, ctx, tender_id)
    row = db.scalar(select(SavedTender).where(SavedTender.organization_id == ctx.org_id, SavedTender.tender_id == t.id))
    if body.state == "none":
        if row:
            db.delete(row)
    elif row:
        row.state = body.state
        row.user_id = ctx.user.id
    else:
        db.add(SavedTender(organization_id=ctx.org_id, tender_id=t.id, state=body.state, user_id=ctx.user.id))
    audit(db, ctx, f"tender.{body.state if body.state != 'none' else 'unsaved'}", "tender", t.id, {"title": t.title[:120]})
    db.commit()
    return {"saved_state": None if body.state == "none" else body.state}


@router.post("/tenders/{tender_id}/notes", status_code=201)
def add_note(tender_id: uuid.UUID, body: NoteIn, ctx: Analyst, db: DB) -> dict[str, Any]:
    t = get_visible_tender(db, ctx, tender_id)
    note = ReviewNote(organization_id=ctx.org_id, tender_id=t.id, author_id=ctx.user.id, body=body.body.strip())
    db.add(note)
    db.commit()
    return {"id": str(note.id), "body": note.body, "author": ctx.user.full_name, "created_at": note.created_at}


@router.patch("/tenders/{tender_id}/requirements/{req_id}")
def review_requirement(
    tender_id: uuid.UUID, req_id: uuid.UUID, body: RequirementReviewIn, ctx: Analyst, db: DB
) -> dict[str, Any]:
    t = get_visible_tender(db, ctx, tender_id)
    if t.visibility_org_id != ctx.org_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only criteria of tenders your company imported can be reviewed")
    req = next((r for r in t.requirements if r.id == req_id), None)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Requirement not found")
    before = {"status": req.verification_status, "threshold_value": req.threshold_value, "threshold_text": req.threshold_text}
    req.verification_status = body.verification_status
    if body.mandatory is not None:
        req.mandatory = body.mandatory
    if body.threshold_value is not None:
        req.threshold_value = body.threshold_value
    if body.threshold_text is not None:
        req.threshold_text = body.threshold_text
    if body.verification_status == "source_verified" and req.extraction_method != "seed":
        req.extraction_method = "human" if (body.threshold_value or body.threshold_text) else req.extraction_method
    audit(db, ctx, "requirement.reviewed", "tender_requirement", req.id, {"before": before, "after": body.model_dump()})
    db.flush()
    db.refresh(t)
    matching.compute_match(db, ctx.org_id, t)
    db.commit()
    return _eligibility_payload(db, ctx, t, _match(db, ctx, t))


@router.get("/views")
def list_views(ctx: Tenant, db: DB) -> dict[str, Any]:
    views = db.scalars(
        select(SavedView).where(SavedView.organization_id == ctx.org_id, SavedView.user_id == ctx.user.id)
        .order_by(SavedView.created_at)
    ).all()
    return {"items": [{"id": str(v.id), "name": v.name, "query": v.query} for v in views]}


@router.post("/views", status_code=201)
def create_view(body: SavedViewIn, ctx: Tenant, db: DB) -> dict[str, Any]:
    v = SavedView(organization_id=ctx.org_id, user_id=ctx.user.id, name=body.name.strip(), query=body.query.lstrip("?"))
    db.add(v)
    db.commit()
    return {"id": str(v.id), "name": v.name, "query": v.query}


@router.delete("/views/{view_id}", status_code=204)
def delete_view(view_id: uuid.UUID, ctx: Tenant, db: DB) -> None:
    v = db.scalar(
        select(SavedView).where(SavedView.id == view_id, SavedView.organization_id == ctx.org_id, SavedView.user_id == ctx.user.id)
    )
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    db.delete(v)
    db.commit()
