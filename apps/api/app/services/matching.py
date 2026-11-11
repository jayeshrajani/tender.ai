"""Persist eligibility + relevance results per company × tender."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Certificate,
    CompanyExperience,
    CompanyPreference,
    CompanyRequirementEvaluation,
    CompanyTenderMatch,
    Organization,
    Tender,
)
from app.services import eligibility, scoring
from app.services.facts import CertFact, CompanyFacts, ExperienceFact, RequirementFact, TenderFacts
from app.services.timeutil import utcnow


def visible_tenders_clause(org_id: uuid.UUID) -> Any:
    """Tenders a company may see: global ones plus its own private imports."""
    return or_(Tender.visibility_org_id.is_(None), Tender.visibility_org_id == org_id)


def _cert_fact(c: Certificate) -> CertFact:
    return CertFact(
        id=c.id,
        cert_type=c.cert_type,
        title=c.title,
        verification_status=c.verification_status,
        expires_on=c.expires_on,
        registration_class=c.registration_class,
        value_paise=c.value_paise,
        has_document=c.document_id is not None,
    )


def load_company_facts(db: Session, org_id: uuid.UUID) -> CompanyFacts:
    org = db.get(Organization, org_id)
    if org is None:
        raise LookupError("organization not found")
    prefs = db.scalar(select(CompanyPreference).where(CompanyPreference.organization_id == org_id))
    certs = db.scalars(select(Certificate).where(Certificate.organization_id == org_id)).all()
    exps = db.scalars(select(CompanyExperience).where(CompanyExperience.organization_id == org_id)).all()
    return CompanyFacts(
        organization_id=org.id,
        gstin=org.gstin,
        pan=org.pan,
        annual_turnover_paise=org.annual_turnover_paise,
        registration_class=org.contractor_registration_class,
        certificates=tuple(_cert_fact(c) for c in certs),
        experiences=tuple(
            ExperienceFact(
                id=e.id,
                project_name=e.project_name,
                category_code=e.category_code,
                value_paise=e.contract_value_paise,
                completed_on=e.completed_on,
                certificate=_cert_fact(e.certificate) if e.certificate else None,
            )
            for e in exps
        ),
        equipment=tuple(org.equipment or ()),
        workforce_count=org.workforce_count,
        max_concurrent_projects=org.max_concurrent_projects,
        current_active_projects=org.current_active_projects,
        category_codes=tuple(prefs.category_codes) if prefs else (),
        subcategory_codes=tuple(prefs.subcategory_codes) if prefs else (),
        specialties=tuple(prefs.specialties) if prefs else (),
        districts=tuple(prefs.districts) if prefs else (),
        base_district=org.base_district,
        operating_radius_km=prefs.operating_radius_km if prefs else None,
        statewide=prefs.statewide if prefs else False,
        min_value_paise=prefs.min_tender_value_paise if prefs else None,
        max_value_paise=prefs.max_tender_value_paise if prefs else None,
    )


def tender_facts(t: Tender) -> TenderFacts:
    return TenderFacts(
        id=t.id,
        title=t.title,
        category_code=t.category_code,
        subcategory_codes=tuple(t.subcategory_codes or ()),
        district=t.district,
        estimated_value_paise=t.estimated_value_paise,
        deadline=t.bid_submission_end_at,
        completion_period_days=t.completion_period_days,
        requirements=tuple(
            RequirementFact(
                id=r.id,
                requirement_type=r.requirement_type,
                label=r.label,
                mandatory=r.mandatory,
                operator=r.operator,
                verification_status=r.verification_status,
                threshold_value=r.threshold_value,
                threshold_text=r.threshold_text,
                unit=r.unit,
                category_code=r.category_code,
            )
            for r in t.requirements
        ),
    )


def compute_match(
    db: Session, org_id: uuid.UUID, tender: Tender, company: CompanyFacts | None = None
) -> tuple[CompanyTenderMatch, bool]:
    """Upsert the match row and its evaluations. Returns (match, changed)."""
    company = company or load_company_facts(db, org_id)
    tf = tender_facts(tender)
    outcome = eligibility.evaluate(company, tf)
    total, breakdown = scoring.score(company, tf)
    digest = hashlib.sha256(
        json.dumps(
            {
                "status": outcome.status,
                "evals": [(str(e.requirement_id), e.result, e.explanation) for e in outcome.evaluations],
                "score": total,
            },
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()

    match = db.scalar(
        select(CompanyTenderMatch).where(
            CompanyTenderMatch.organization_id == org_id, CompanyTenderMatch.tender_id == tender.id
        )
    )
    changed = match is None or match.inputs_hash != digest
    if match is None:
        match = CompanyTenderMatch(organization_id=org_id, tender_id=tender.id)
        db.add(match)
    match.eligibility_status = outcome.status
    match.eligibility_summary = outcome.summary
    match.mandatory_failures = outcome.mandatory_failures
    match.unknown_count = outcome.unknown_count
    match.relevance_score = total
    match.score_breakdown = breakdown
    match.tender_version = tender.version
    match.inputs_hash = digest
    match.computed_at = utcnow()
    db.flush()

    if changed:
        db.execute(
            delete(CompanyRequirementEvaluation).where(CompanyRequirementEvaluation.match_id == match.id)
        )
        for ev in outcome.evaluations:
            db.add(
                CompanyRequirementEvaluation(
                    organization_id=org_id,
                    match_id=match.id,
                    requirement_id=ev.requirement_id,
                    result=ev.result,
                    explanation=ev.explanation,
                    company_evidence=ev.evidence,
                )
            )
        db.flush()
    return match, changed


def recompute_for_org(db: Session, org_id: uuid.UUID) -> dict[str, int]:
    company = load_company_facts(db, org_id)
    tenders = db.scalars(
        select(Tender).where(visible_tenders_clause(org_id), Tender.duplicate_of_id.is_(None))
    ).all()
    changed = 0
    for t in tenders:
        _, c = compute_match(db, org_id, t, company)
        changed += int(c)
    return {"evaluated": len(tenders), "changed": changed}


def recompute_all(db: Session) -> dict[str, int]:
    totals = {"organizations": 0, "evaluated": 0, "changed": 0}
    for org_id in db.scalars(select(Organization.id)).all():
        stats = recompute_for_org(db, org_id)
        totals["organizations"] += 1
        totals["evaluated"] += stats["evaluated"]
        totals["changed"] += stats["changed"]
    return totals
