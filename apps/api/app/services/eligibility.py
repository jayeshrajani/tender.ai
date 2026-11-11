"""Deterministic eligibility engine.

Rules (documented in README):
- Requirement results: PASS, FAIL, UNKNOWN, NOT_APPLICABLE.
- A FAIL on a mandatory, source-verified requirement → NOT_ELIGIBLE.
- ELIGIBLE only when every mandatory requirement PASSes, each requirement is
  source-verified, and company evidence is verified and unexpired.
- Anything else → NEEDS_VERIFICATION. No requirements extracted → NEEDS_VERIFICATION.
- Expired or unverified certificates never PASS.
- AI output can only create ``needs_review`` requirements, so it can never produce a
  confirmed failure or override one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.models import EligibilityStatus, RequirementResult, RequirementReview
from app.services.facts import CertFact, CompanyFacts, RequirementFact, TenderFacts
from app.services.money import format_inr
from app.services.timeutil import to_ist, today_ist

# Contractor registration classes, lowest → highest. Configurable per state scheme.
REGISTRATION_CLASS_RANK = {"D": 1, "C": 2, "B": 3, "A": 4, "AA": 5}

CERT_LABELS = {
    "gst": "GST registration",
    "pan": "PAN",
    "epf": "EPF registration",
    "esic": "ESIC registration",
    "labour_licence": "Labour licence",
    "electrical_licence": "Electrical contractor licence",
    "udyam": "Udyam (MSME) registration",
    "turnover_certificate": "CA-certified turnover statement",
    "solvency": "Solvency certificate",
    "contractor_registration": "Contractor registration",
    "iso": "ISO certification",
}


@dataclass
class Evaluation:
    requirement_id: Any
    result: RequirementResult
    explanation: str
    evidence: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class EligibilityOutcome:
    status: EligibilityStatus
    summary: str
    evaluations: list[Evaluation]
    mandatory_failures: int
    unknown_count: int


def _cert_state(cert: CertFact, as_of: date) -> tuple[bool, str]:
    """(usable, reason). Usable = verified and not expired as of the reference date."""
    if cert.expires_on is not None and cert.expires_on < as_of:
        return False, f"{cert.title} expired on {cert.expires_on:%d %b %Y}"
    if cert.verification_status != "verified":
        if not cert.has_document:
            return False, f"{cert.title} has no uploaded document"
        return False, f"{cert.title} is uploaded but not yet verified"
    return True, f"{cert.title} verified"


def _cert_evidence(cert: CertFact) -> dict[str, Any]:
    return {
        "kind": "certificate",
        "id": str(cert.id),
        "title": cert.title,
        "verification_status": cert.verification_status,
        "expires_on": cert.expires_on.isoformat() if cert.expires_on else None,
    }


def _best_cert(company: CompanyFacts, cert_type: str, as_of: date) -> CertFact | None:
    certs = [c for c in company.certificates if c.cert_type == cert_type]
    if not certs:
        return None
    return sorted(certs, key=lambda c: (_cert_state(c, as_of)[0], c.expires_on or date.max))[-1]


def _eval_turnover(req: RequirementFact, company: CompanyFacts, as_of: date) -> Evaluation:
    need = req.threshold_value or 0
    have = company.annual_turnover_paise
    if have is None:
        return Evaluation(req.id, RequirementResult.UNKNOWN, "Annual turnover is not recorded in the company profile.")
    evidence: list[dict[str, Any]] = [{"kind": "profile", "field": "annual_turnover", "value": format_inr(have)}]
    if have < need:
        return Evaluation(
            req.id,
            RequirementResult.FAIL,
            f"Declared turnover {format_inr(have)} is below the required {format_inr(need)}.",
            evidence,
        )
    cert = _best_cert(company, "turnover_certificate", as_of)
    if cert is None:
        return Evaluation(
            req.id,
            RequirementResult.UNKNOWN,
            f"Declared turnover {format_inr(have)} meets {format_inr(need)}, but no CA-certified turnover statement is on file.",
            evidence,
        )
    usable, reason = _cert_state(cert, as_of)
    evidence.append(_cert_evidence(cert))
    if not usable:
        return Evaluation(
            req.id,
            RequirementResult.UNKNOWN,
            f"Declared turnover meets the threshold, but {reason}.",
            evidence,
        )
    return Evaluation(
        req.id,
        RequirementResult.PASS,
        f"Turnover {format_inr(have)} ≥ {format_inr(need)}; {reason}.",
        evidence,
    )


def _eval_similar_work(
    req: RequirementFact, company: CompanyFacts, tender: TenderFacts, as_of: date
) -> Evaluation:
    need_value = req.threshold_value or 0
    need_count = int(req.threshold_text or 1) if (req.threshold_text or "1").isdigit() else 1
    category = req.category_code or tender.category_code
    if not company.experiences:
        return Evaluation(req.id, RequirementResult.UNKNOWN, "No completed projects are recorded in the company profile.")
    qualifying = [
        e for e in company.experiences
        if (category is None or e.category_code == category) and e.value_paise >= need_value
    ]
    qualifying.sort(key=lambda e: e.value_paise, reverse=True)
    noun = "work" if need_count == 1 else "works"
    if len(qualifying) < need_count:
        return Evaluation(
            req.id,
            RequirementResult.FAIL,
            f"Needs {need_count} similar {noun} of at least {format_inr(need_value)}; "
            f"recorded experience has {len(qualifying)}.",
            [{"kind": "experience", "id": str(e.id), "title": e.project_name} for e in qualifying],
        )
    verified = [e for e in qualifying if e.certificate and _cert_state(e.certificate, as_of)[0]]
    evidence = [
        {
            "kind": "experience",
            "id": str(e.id),
            "title": e.project_name,
            "value": format_inr(e.value_paise),
            "certificate_verified": bool(e.certificate and _cert_state(e.certificate, as_of)[0]),
        }
        for e in qualifying[: max(need_count, 3)]
    ]
    if len(verified) >= need_count:
        return Evaluation(
            req.id,
            RequirementResult.PASS,
            f"{len(verified)} qualifying {noun} with verified completion certificates "
            f"(largest {format_inr(verified[0].value_paise)}).",
            evidence,
        )
    return Evaluation(
        req.id,
        RequirementResult.UNKNOWN,
        f"{len(qualifying)} qualifying {noun} recorded, but only {len(verified)} "
        "have a verified completion certificate.",
        evidence,
    )


def _eval_registration(req: RequirementFact, company: CompanyFacts, as_of: date) -> Evaluation:
    required = (req.threshold_text or "").upper()
    need_rank = REGISTRATION_CLASS_RANK.get(required)
    cert = _best_cert(company, "contractor_registration", as_of)
    have_class = ((cert.registration_class if cert else None) or company.registration_class or "").upper()
    have_rank = REGISTRATION_CLASS_RANK.get(have_class)
    evidence = [_cert_evidence(cert)] if cert else []
    if have_rank is None:
        return Evaluation(req.id, RequirementResult.UNKNOWN, "Contractor registration class is not recorded.", evidence)
    if need_rank is not None and have_rank < need_rank:
        return Evaluation(
            req.id,
            RequirementResult.FAIL,
            f"Registered as Class {have_class}; tender requires Class {required} or above.",
            evidence,
        )
    if cert is None:
        return Evaluation(
            req.id,
            RequirementResult.UNKNOWN,
            f"Class {have_class} declared, but no registration certificate is on file.",
            evidence,
        )
    usable, reason = _cert_state(cert, as_of)
    if not usable:
        return Evaluation(req.id, RequirementResult.UNKNOWN, f"Class {have_class} meets the class, but {reason}.", evidence)
    return Evaluation(
        req.id, RequirementResult.PASS, f"Class {have_class} ≥ Class {required or 'required'}; {reason}.", evidence
    )


def _eval_certificate(req: RequirementFact, company: CompanyFacts, as_of: date) -> Evaluation:
    cert_type = (req.threshold_text or "").lower()
    label = CERT_LABELS.get(cert_type, cert_type.replace("_", " ") or "Certificate")
    cert = _best_cert(company, cert_type, as_of)
    if cert is None:
        declared = {"gst": company.gstin, "pan": company.pan}.get(cert_type)
        if declared:
            return Evaluation(
                req.id,
                RequirementResult.UNKNOWN,
                f"{label} number is in the profile, but no certificate is uploaded.",
                [{"kind": "profile", "field": cert_type, "value": declared}],
            )
        return Evaluation(req.id, RequirementResult.UNKNOWN, f"No {label} on file.")
    usable, reason = _cert_state(cert, as_of)
    result = RequirementResult.PASS if usable else RequirementResult.UNKNOWN
    return Evaluation(req.id, result, f"{reason[0].upper()}{reason[1:]}.", [_cert_evidence(cert)])


def _eval_solvency(req: RequirementFact, company: CompanyFacts, as_of: date) -> Evaluation:
    need = req.threshold_value or 0
    cert = _best_cert(company, "solvency", as_of)
    if cert is None:
        return Evaluation(req.id, RequirementResult.UNKNOWN, f"No solvency certificate on file (needs {format_inr(need)}).")
    evidence = [_cert_evidence(cert)]
    if cert.value_paise is not None and cert.value_paise < need:
        return Evaluation(
            req.id,
            RequirementResult.FAIL,
            f"Solvency {format_inr(cert.value_paise)} is below the required {format_inr(need)}.",
            evidence,
        )
    usable, reason = _cert_state(cert, as_of)
    if cert.value_paise is None or not usable:
        detail = reason if not usable else "certificate amount not recorded"
        return Evaluation(req.id, RequirementResult.UNKNOWN, f"Solvency cannot be confirmed: {detail}.", evidence)
    return Evaluation(
        req.id, RequirementResult.PASS, f"Solvency {format_inr(cert.value_paise)} ≥ {format_inr(need)}; {reason}.", evidence
    )


def _eval_equipment(req: RequirementFact, company: CompanyFacts) -> Evaluation:
    item = (req.threshold_text or "").lower()
    match = next((e for e in company.equipment if item and item in e.lower()), None)
    if match:
        return Evaluation(
            req.id,
            RequirementResult.PASS,
            f"'{match}' is listed in the company equipment register (self-declared; ownership/lease proof is submitted with the bid).",
            [{"kind": "profile", "field": "equipment", "value": match}],
        )
    return Evaluation(req.id, RequirementResult.UNKNOWN, f"'{req.threshold_text}' is not listed in the equipment register.")


def evaluate_requirement(
    req: RequirementFact, company: CompanyFacts, tender: TenderFacts, as_of: date
) -> Evaluation:
    if req.operator == "info":
        return Evaluation(req.id, RequirementResult.NOT_APPLICABLE, "Informational condition; no company check needed.")
    match req.requirement_type:
        case "annual_turnover":
            return _eval_turnover(req, company, as_of)
        case "similar_work":
            return _eval_similar_work(req, company, tender, as_of)
        case "contractor_registration":
            return _eval_registration(req, company, as_of)
        case "certificate":
            return _eval_certificate(req, company, as_of)
        case "solvency":
            return _eval_solvency(req, company, as_of)
        case "equipment":
            return _eval_equipment(req, company)
        case "bid_capacity":
            return Evaluation(
                req.id,
                RequirementResult.UNKNOWN,
                "Bid capacity (A×N×2 − B) must be computed from audited figures and current commitments; not automated in V1.",
            )
        case _:
            return Evaluation(req.id, RequirementResult.UNKNOWN, "This criterion type needs manual verification.")


def evaluate(company: CompanyFacts, tender: TenderFacts, today: date | None = None) -> EligibilityOutcome:
    # Certificates must be valid on the submission date, not just today.
    as_of = today or today_ist()
    if tender.deadline is not None:
        as_of = max(as_of, to_ist(tender.deadline).date())

    active = [r for r in tender.requirements if r.verification_status != RequirementReview.rejected]
    evaluations = [evaluate_requirement(r, company, tender, as_of) for r in active]
    by_id = {e.requirement_id: e for e in evaluations}

    mandatory = [r for r in active if r.mandatory and by_id[r.id].result != RequirementResult.NOT_APPLICABLE]
    confirmed_fail = [
        r for r in mandatory
        if by_id[r.id].result == RequirementResult.FAIL
        and r.verification_status == RequirementReview.source_verified
    ]
    unconfirmed = [
        r for r in mandatory
        if by_id[r.id].result != RequirementResult.PASS
        or r.verification_status != RequirementReview.source_verified
    ]
    unknown_count = sum(1 for e in evaluations if e.result == RequirementResult.UNKNOWN)

    if not mandatory:
        return EligibilityOutcome(
            EligibilityStatus.NEEDS_VERIFICATION,
            "No mandatory eligibility criteria have been extracted from source documents yet.",
            evaluations,
            0,
            unknown_count,
        )
    if confirmed_fail:
        labels = "; ".join(r.label for r in confirmed_fail[:2])
        more = f" (+{len(confirmed_fail) - 2} more)" if len(confirmed_fail) > 2 else ""
        return EligibilityOutcome(
            EligibilityStatus.NOT_ELIGIBLE, f"Fails: {labels}{more}.", evaluations, len(confirmed_fail), unknown_count
        )
    if not unconfirmed:
        return EligibilityOutcome(
            EligibilityStatus.ELIGIBLE,
            f"All {len(mandatory)} mandatory criteria met with verified evidence.",
            evaluations,
            0,
            unknown_count,
        )
    first = unconfirmed[0]
    reason = (
        "criterion awaiting review against the source document"
        if first.verification_status != RequirementReview.source_verified
        else by_id[first.id].explanation.rstrip(".")
    )
    passed = len(mandatory) - len(unconfirmed)
    return EligibilityOutcome(
        EligibilityStatus.NEEDS_VERIFICATION,
        f"{passed} of {len(mandatory)} mandatory criteria confirmed. Next: {first.label} — {reason}.",
        evaluations,
        0,
        unknown_count,
    )
