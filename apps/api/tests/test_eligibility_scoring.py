import uuid
from datetime import UTC, date, datetime, timedelta

from app.models import EligibilityStatus, RequirementResult
from app.services import eligibility, scoring
from app.services.facts import CertFact, CompanyFacts, ExperienceFact, RequirementFact, TenderFacts

TODAY = date(2026, 11, 11)
NOW = datetime(2026, 11, 11, 6, 0, tzinfo=UTC)
CR = 100 * 10_000_000


def cert(kind: str, verified: bool = True, expires: date | None = None, **kw) -> CertFact:  # type: ignore[no-untyped-def]
    return CertFact(uuid.uuid4(), kind, kind, "verified" if verified else "unverified", expires, has_document=True, **kw)


def req(kind: str, **kw) -> RequirementFact:  # type: ignore[no-untyped-def]
    defaults = {"label": kind, "mandatory": True, "operator": "gte", "verification_status": "source_verified"}
    return RequirementFact(uuid.uuid4(), kind, **{**defaults, **kw})


def tender(*reqs: RequirementFact, value: int = 5 * CR, days: int = 20, category: str = "roads") -> TenderFacts:
    return TenderFacts(uuid.uuid4(), "BT road", category, (), "Bhopal", value, NOW + timedelta(days=days),
                       requirements=tuple(reqs))


def company(**kw) -> CompanyFacts:  # type: ignore[no-untyped-def]
    base = dict(
        organization_id=uuid.uuid4(), annual_turnover_paise=10 * CR, registration_class="A",
        certificates=(cert("turnover_certificate"), cert("contractor_registration", registration_class="A",
                                                         expires=TODAY + timedelta(days=400)), cert("gst")),
        experiences=(ExperienceFact(uuid.uuid4(), "Road", "roads", 6 * CR, certificate=cert("experience")),),
    )
    return CompanyFacts(**{**base, **kw})


def test_all_mandatory_pass_is_eligible() -> None:
    t = tender(req("annual_turnover", threshold_value=5 * CR), req("contractor_registration", threshold_text="B"),
               req("certificate", operator="exists", threshold_text="gst"),
               req("similar_work", threshold_value=4 * CR, threshold_text="1"))
    out = eligibility.evaluate(company(), t, TODAY)
    assert out.status == EligibilityStatus.ELIGIBLE
    assert all(e.result == RequirementResult.PASS for e in out.evaluations)


def test_confirmed_mandatory_failure_is_not_eligible() -> None:
    t = tender(req("annual_turnover", threshold_value=20 * CR), req("certificate", operator="exists", threshold_text="gst"))
    out = eligibility.evaluate(company(), t, TODAY)
    assert out.status == EligibilityStatus.NOT_ELIGIBLE
    assert out.mandatory_failures == 1
    assert out.evaluations[0].result == RequirementResult.FAIL


def test_missing_evidence_needs_verification() -> None:
    t = tender(req("certificate", operator="exists", threshold_text="epf"))
    out = eligibility.evaluate(company(), t, TODAY)
    assert out.status == EligibilityStatus.NEEDS_VERIFICATION
    assert out.evaluations[0].result == RequirementResult.UNKNOWN


def test_expired_certificate_never_passes() -> None:
    expired = cert("labour_licence", expires=TODAY - timedelta(days=1))
    c = company(certificates=company().certificates + (expired,))
    out = eligibility.evaluate(c, tender(req("certificate", operator="exists", threshold_text="labour_licence")), TODAY)
    assert out.evaluations[0].result == RequirementResult.UNKNOWN
    assert "expired" in out.evaluations[0].explanation
    assert out.status != EligibilityStatus.ELIGIBLE


def test_certificate_expiring_before_deadline_does_not_pass() -> None:
    soon = cert("epf", expires=TODAY + timedelta(days=5))
    c = company(certificates=company().certificates + (soon,))
    out = eligibility.evaluate(c, tender(req("certificate", operator="exists", threshold_text="epf"), days=10), TODAY)
    assert out.evaluations[0].result == RequirementResult.UNKNOWN


def test_unverified_certificate_cannot_silently_pass() -> None:
    c = company(certificates=(cert("turnover_certificate", verified=False),))
    out = eligibility.evaluate(c, tender(req("annual_turnover", threshold_value=5 * CR)), TODAY)
    assert out.evaluations[0].result == RequirementResult.UNKNOWN
    assert out.status == EligibilityStatus.NEEDS_VERIFICATION


def test_unreviewed_extraction_failure_is_not_a_confirmed_failure() -> None:
    t = tender(req("annual_turnover", threshold_value=50 * CR, verification_status="needs_review"))
    out = eligibility.evaluate(company(), t, TODAY)
    assert out.evaluations[0].result == RequirementResult.FAIL
    assert out.status == EligibilityStatus.NEEDS_VERIFICATION


def test_no_requirements_extracted_needs_verification() -> None:
    out = eligibility.evaluate(company(), tender(), TODAY)
    assert out.status == EligibilityStatus.NEEDS_VERIFICATION
    assert "No mandatory" in out.summary


def test_informational_condition_is_not_applicable() -> None:
    out = eligibility.evaluate(company(), tender(req("information", operator="info", mandatory=False)), TODAY)
    assert out.evaluations[0].result == RequirementResult.NOT_APPLICABLE


def test_rejected_requirements_are_ignored() -> None:
    t = tender(req("annual_turnover", threshold_value=50 * CR, verification_status="rejected"),
               req("certificate", operator="exists", threshold_text="gst"))
    out = eligibility.evaluate(company(), t, TODAY)
    assert out.status == EligibilityStatus.ELIGIBLE


def test_similar_work_fail_vs_unknown() -> None:
    c = company()
    assert eligibility.evaluate(c, tender(req("similar_work", threshold_value=9 * CR, threshold_text="1")), TODAY).evaluations[0].result == RequirementResult.FAIL
    no_cert = company(experiences=(ExperienceFact(uuid.uuid4(), "Road", "roads", 6 * CR),))
    assert eligibility.evaluate(no_cert, tender(req("similar_work", threshold_value=4 * CR, threshold_text="1")), TODAY).evaluations[0].result == RequirementResult.UNKNOWN
    empty = company(experiences=())
    assert eligibility.evaluate(empty, tender(req("similar_work", threshold_value=1, threshold_text="1")), TODAY).evaluations[0].result == RequirementResult.UNKNOWN


# --- relevance -------------------------------------------------------------


def test_weights_total_100() -> None:
    assert sum(scoring.WEIGHTS.values()) == 100


def test_score_upper_boundary_is_100() -> None:
    c = company(category_codes=("roads",), subcategory_codes=("roads_bituminous",), districts=("Bhopal",),
                min_value_paise=1 * CR, max_value_paise=10 * CR, max_concurrent_projects=5, current_active_projects=0,
                annual_turnover_paise=100 * CR)
    t = TenderFacts(uuid.uuid4(), "BT road", "roads", ("roads_bituminous",), "Bhopal", 5 * CR, NOW + timedelta(days=30))
    total, breakdown = scoring.score(c, t, NOW)
    assert total == 100
    assert {f["key"] for f in breakdown} == set(scoring.WEIGHTS)


def test_score_lower_boundary_is_0() -> None:
    c = company(category_codes=("electrical",), districts=("Indore",), experiences=(),
                min_value_paise=1 * CR, max_value_paise=2 * CR, max_concurrent_projects=3, current_active_projects=3,
                annual_turnover_paise=1 * CR)
    t = TenderFacts(uuid.uuid4(), "Canal lining", "irrigation", (), "Rewa", 400 * CR, NOW - timedelta(days=1))
    total, breakdown = scoring.score(c, t, NOW)
    assert 0 <= total < 3
    assert all(0 <= f["points"] <= f["weight"] for f in breakdown)


def test_relevance_independent_of_eligibility() -> None:
    c = company(category_codes=("roads",), districts=("Bhopal",), min_value_paise=1 * CR, max_value_paise=10 * CR)
    t = tender(req("annual_turnover", threshold_value=500 * CR))
    total, _ = scoring.score(c, t, NOW)
    out = eligibility.evaluate(c, t, TODAY)
    assert total > 60
    assert out.status == EligibilityStatus.NOT_ELIGIBLE
