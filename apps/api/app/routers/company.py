from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select

from app.deps import DB, Admin, Analyst, Tenant, TenantContext, audit
from app.models import (
    Certificate,
    CompanyDocument,
    CompanyExperience,
    CompanyPreference,
    Organization,
)
from app.schemas import (
    BUSINESS_TYPES,
    CERT_TYPES,
    REG_CLASSES,
    CertificateIn,
    CertificateVerifyIn,
    ExperienceIn,
    ProfileIn,
)
from app.services import matching
from app.services.districts import MP_DISTRICTS
from app.services.eligibility import CERT_LABELS
from app.services.storage import get_storage, new_key, sign_download
from app.services.taxonomy import CATEGORIES
from app.services.timeutil import today_ist, utcnow
from app.services.uploads import UploadError, validate_upload

router = APIRouter(prefix="/api/v1/company", tags=["company"])

ORG_FIELDS = (
    "legal_name", "business_type", "gstin", "pan", "contact_name", "contact_email", "contact_phone",
    "address", "base_district", "annual_turnover_paise", "turnover_financial_year",
    "contractor_registration_class", "registration_authority", "workforce_count", "equipment",
    "available_resources", "max_concurrent_projects", "current_active_projects",
)
PREF_FIELDS = (
    "category_codes", "subcategory_codes", "specialties", "districts", "operating_radius_km",
    "statewide", "min_tender_value_paise", "max_tender_value_paise",
)


def _prefs(db: DB, org_id: uuid.UUID) -> CompanyPreference:
    prefs = db.scalar(select(CompanyPreference).where(CompanyPreference.organization_id == org_id))
    if prefs is None:
        prefs = CompanyPreference(organization_id=org_id)
        db.add(prefs)
        db.flush()
    return prefs


def _cert_json(c: Certificate) -> dict[str, Any]:
    today = today_ist()
    expiry_state = "none"
    if c.expires_on:
        if c.expires_on < today:
            expiry_state = "expired"
        elif c.expires_on <= today + timedelta(days=60):
            expiry_state = "expiring"
        else:
            expiry_state = "valid"
    return {
        "id": str(c.id), "cert_type": c.cert_type, "type_label": CERT_LABELS.get(c.cert_type, c.cert_type),
        "title": c.title, "number": c.number, "issuer": c.issuer,
        "issued_on": c.issued_on, "expires_on": c.expires_on, "expiry_state": expiry_state,
        "registration_class": c.registration_class, "value_paise": c.value_paise,
        "verification_status": c.verification_status, "verified_at": c.verified_at,
        "notes": c.notes,
        "document": (
            {"id": str(c.document.id), "filename": c.document.original_filename,
             "size_bytes": c.document.size_bytes, "content_type": c.document.content_type}
            if c.document else None
        ),
    }


def profile_payload(db: DB, ctx: TenantContext) -> dict[str, Any]:
    org = db.get(Organization, ctx.org_id)
    assert org is not None
    prefs = _prefs(db, ctx.org_id)
    exps = db.scalars(
        select(CompanyExperience).where(CompanyExperience.organization_id == ctx.org_id)
        .order_by(CompanyExperience.completed_on.desc().nulls_last())
    ).all()
    certs = db.scalars(
        select(Certificate).where(Certificate.organization_id == ctx.org_id).order_by(Certificate.created_at)
    ).all()
    return {
        "id": str(org.id),
        **{f: getattr(org, f) for f in ORG_FIELDS},
        **{f: getattr(prefs, f) for f in PREF_FIELDS},
        "onboarding_step": org.onboarding_step,
        "onboarding_completed_at": org.onboarding_completed_at,
        "is_demo": org.is_demo,
        "experience": [
            {
                "id": str(e.id), "project_name": e.project_name, "client_name": e.client_name,
                "category_code": e.category_code, "district": e.district,
                "contract_value_paise": e.contract_value_paise, "completed_on": e.completed_on,
                "certificate_id": str(e.certificate_id) if e.certificate_id else None,
                "certificate_status": e.certificate.verification_status if e.certificate else None,
            }
            for e in exps
        ],
        "certificates": [_cert_json(c) for c in certs],
        "role": ctx.role,
    }


@router.get("/reference")
def reference() -> dict[str, Any]:
    return {
        "categories": [
            {"code": c.code, "name": c.name, "name_hi": c.name_hi,
             "subcategories": [{"code": s.code, "name": s.name} for s in c.subs]}
            for c in CATEGORIES
        ],
        "districts": sorted(MP_DISTRICTS),
        "registration_classes": list(REG_CLASSES),
        "business_types": list(BUSINESS_TYPES),
        "certificate_types": [{"code": t, "label": CERT_LABELS.get(t, t.replace("_", " ").title())} for t in CERT_TYPES],
    }


@router.get("/profile")
def get_profile(ctx: Tenant, db: DB) -> dict[str, Any]:
    return profile_payload(db, ctx)


@router.put("/profile")
def put_profile(body: ProfileIn, ctx: Admin, db: DB) -> dict[str, Any]:
    org = db.get(Organization, ctx.org_id)
    assert org is not None
    prefs = _prefs(db, ctx.org_id)
    data = body.model_dump(exclude_unset=True)
    changed = []
    for f in ORG_FIELDS:
        if f in data:
            if f == "legal_name" and not data[f]:
                continue
            setattr(org, f, [] if f == "equipment" and data[f] is None else data[f])
            changed.append(f)
    for f in PREF_FIELDS:
        if f in data:
            value = data[f]
            if f in ("category_codes", "subcategory_codes", "specialties", "districts") and value is None:
                value = []
            if f == "statewide" and value is None:
                value = False
            setattr(prefs, f, value)
            changed.append(f)
    if body.step is not None:
        org.onboarding_step = max(org.onboarding_step, body.step)
    if body.complete and org.onboarding_completed_at is None:
        org.onboarding_completed_at = utcnow()
        org.onboarding_step = 6
    audit(db, ctx, "company.profile_updated", "organization", org.id, {"fields": changed})
    db.flush()
    matching.recompute_for_org(db, ctx.org_id)
    db.commit()
    return profile_payload(db, ctx)


@router.post("/experience", status_code=201)
def add_experience(body: ExperienceIn, ctx: Admin, db: DB) -> dict[str, Any]:
    cert_id = _own_cert(db, ctx, body.certificate_id)
    exp = CompanyExperience(organization_id=ctx.org_id, **body.model_dump(exclude={"certificate_id"}), certificate_id=cert_id)
    db.add(exp)
    audit(db, ctx, "experience.added", "company_experience", None, {"project": body.project_name})
    db.flush()
    matching.recompute_for_org(db, ctx.org_id)
    db.commit()
    return profile_payload(db, ctx)


@router.delete("/experience/{exp_id}")
def delete_experience(exp_id: uuid.UUID, ctx: Admin, db: DB) -> dict[str, Any]:
    exp = db.scalar(
        select(CompanyExperience).where(CompanyExperience.id == exp_id, CompanyExperience.organization_id == ctx.org_id)
    )
    if exp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    db.delete(exp)
    audit(db, ctx, "experience.deleted", "company_experience", exp_id)
    db.flush()
    matching.recompute_for_org(db, ctx.org_id)
    db.commit()
    return profile_payload(db, ctx)


def _own_cert(db: DB, ctx: TenantContext, cert_id: str | None) -> uuid.UUID | None:
    if not cert_id:
        return None
    try:
        cid = uuid.UUID(cert_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid certificate id") from exc
    if not db.scalar(select(Certificate.id).where(Certificate.id == cid, Certificate.organization_id == ctx.org_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Certificate not found")
    return cid


def _store_document(db: DB, ctx: TenantContext, file: UploadFile, data: bytes) -> CompanyDocument:
    try:
        up = validate_upload(file.filename, data, {"pdf", "jpg", "jpeg", "png"})
    except UploadError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    key = new_key("company-docs", ctx.org_id, up.ext)
    get_storage().put(key, up.data, up.content_type)
    doc = CompanyDocument(
        organization_id=ctx.org_id, original_filename=up.filename, content_type=up.content_type,
        size_bytes=up.size, sha256=up.sha256, storage_key=key, uploaded_by_id=ctx.user.id,
    )
    db.add(doc)
    db.flush()
    return doc


@router.get("/documents")
def list_documents(ctx: Tenant, db: DB) -> dict[str, Any]:
    certs = db.scalars(
        select(Certificate).where(Certificate.organization_id == ctx.org_id).order_by(Certificate.expires_on.asc().nulls_last())
    ).all()
    return {"certificates": [_cert_json(c) for c in certs]}


@router.post("/documents", status_code=201)
async def upload_document(
    ctx: Admin,
    db: DB,
    file: UploadFile | None = File(default=None),
    cert_type: str = Form(...),
    title: str = Form(...),
    number: str | None = Form(default=None),
    issuer: str | None = Form(default=None),
    issued_on: str | None = Form(default=None),
    expires_on: str | None = Form(default=None),
    registration_class: str | None = Form(default=None),
    value_paise: int | None = Form(default=None),
    certificate_id: str | None = Form(default=None),
) -> dict[str, Any]:
    """Create a certificate record (optionally with a PDF/JPG/PNG file) or attach a file to one."""
    payload = CertificateIn.model_validate(
        {
            "cert_type": cert_type, "title": title, "number": number or None, "issuer": issuer or None,
            "issued_on": issued_on or None, "expires_on": expires_on or None,
            "registration_class": registration_class or None, "value_paise": value_paise,
        }
    )
    doc = None
    if file is not None and file.filename:
        data = await file.read()
        doc = _store_document(db, ctx, file, data)
    if certificate_id:
        cid = _own_cert(db, ctx, certificate_id)
        cert = db.get(Certificate, cid)
        assert cert is not None
        for k, v in payload.model_dump().items():
            if k != "notes":
                setattr(cert, k, v)
        cert.verification_status = "unverified"
        cert.verified_at = None
    else:
        cert = Certificate(organization_id=ctx.org_id, **payload.model_dump())
        db.add(cert)
    if doc is not None:
        cert.document_id = doc.id
        # A new file always needs fresh verification.
        cert.verification_status = "unverified"
    db.flush()
    audit(db, ctx, "certificate.saved", "certificate", cert.id, {"type": cert.cert_type, "file": bool(doc)})
    matching.recompute_for_org(db, ctx.org_id)
    db.commit()
    db.refresh(cert)
    return _cert_json(cert)


@router.patch("/certificates/{cert_id}/verification")
def verify_certificate(cert_id: uuid.UUID, body: CertificateVerifyIn, ctx: Admin, db: DB) -> dict[str, Any]:
    cert = db.scalar(select(Certificate).where(Certificate.id == cert_id, Certificate.organization_id == ctx.org_id))
    if cert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if body.verification_status == "verified" and cert.document_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Upload the certificate file before verifying")
    cert.verification_status = body.verification_status
    cert.verified_by_id = ctx.user.id if body.verification_status == "verified" else None
    cert.verified_at = utcnow() if body.verification_status == "verified" else None
    audit(db, ctx, f"certificate.{body.verification_status}", "certificate", cert.id, {"title": cert.title})
    db.flush()
    matching.recompute_for_org(db, ctx.org_id)
    db.commit()
    return _cert_json(cert)


@router.delete("/certificates/{cert_id}", status_code=204)
def delete_certificate(cert_id: uuid.UUID, ctx: Admin, db: DB) -> Response:
    cert = db.scalar(select(Certificate).where(Certificate.id == cert_id, Certificate.organization_id == ctx.org_id))
    if cert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    db.delete(cert)
    audit(db, ctx, "certificate.deleted", "certificate", cert_id, {"title": cert.title})
    db.flush()
    matching.recompute_for_org(db, ctx.org_id)
    db.commit()
    return Response(status_code=204)


@router.get("/documents/{doc_id}/link")
def document_link(doc_id: uuid.UUID, ctx: Analyst, db: DB) -> dict[str, str]:
    doc = db.scalar(
        select(CompanyDocument).where(CompanyDocument.id == doc_id, CompanyDocument.organization_id == ctx.org_id)
    )
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    token = sign_download(doc.storage_key, ctx.org_id, doc.original_filename, doc.content_type)
    audit(db, ctx, "document.link_issued", "company_document", doc.id)
    db.commit()
    return {"url": f"/api/v1/files/{token}", "expires_in": "300"}
