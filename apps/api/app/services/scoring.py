"""Relevance scoring (0–100), kept separate from eligibility.

Weights: specialisation 25, location 15, value suitability 15, similar experience 20,
operational capacity 15, preparation time 10. Each factor yields a fraction in [0, 1];
points = weight × fraction. Rules are documented in README → "Relevance score".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from app.services.districts import distance_km
from app.services.facts import CompanyFacts, TenderFacts
from app.services.money import format_inr
from app.services.taxonomy import RELATED
from app.services.timeutil import utcnow

WEIGHTS = {
    "specialization": 25,
    "location": 15,
    "value": 15,
    "experience": 20,
    "capacity": 15,
    "time": 10,
}
LABELS = {
    "specialization": "Specialisation match",
    "location": "Location match",
    "value": "Tender value suitability",
    "experience": "Similar completed experience",
    "capacity": "Operational capacity",
    "time": "Time to prepare",
}


@dataclass
class Factor:
    key: str
    label: str
    weight: int
    fraction: float
    points: float
    reason: str


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _specialization(c: CompanyFacts, t: TenderFacts) -> tuple[float, str]:
    if not t.category_code:
        return 0.3, "Tender work category could not be classified."
    if not c.category_codes:
        return 0.0, "No work categories selected in the company profile."
    if t.category_code in c.category_codes:
        sub_overlap = set(t.subcategory_codes) & set(c.subcategory_codes)
        text = t.title.lower()
        specialty_hit = next((s for s in c.specialties if s and s.lower() in text), None)
        if sub_overlap or specialty_hit:
            return 1.0, "Matches your category and a preferred specialty."
        return 0.8, "Matches one of your work categories."
    if RELATED.get(t.category_code, frozenset()) & set(c.category_codes):
        return 0.4, "Related to your work categories."
    return 0.0, "Outside your selected work categories."


def _location(c: CompanyFacts, t: TenderFacts) -> tuple[float, str]:
    if not t.district:
        return 0.3, "Tender district not stated."
    if t.district in c.districts:
        return 1.0, f"{t.district} is a preferred district."
    anchors = list(c.districts) + ([c.base_district] if c.base_district else [])
    if c.operating_radius_km and anchors:
        dists = [d for a in anchors if (d := distance_km(a, t.district)) is not None]
        if dists:
            nearest = min(dists)
            if nearest <= c.operating_radius_km:
                return _clamp(0.9 - 0.4 * nearest / c.operating_radius_km), (
                    f"≈{nearest:.0f} km from your operating base (within {c.operating_radius_km} km radius)."
                )
    if c.statewide:
        return 0.4, "Outside preferred districts; you accept statewide work."
    return 0.0, f"{t.district} is outside your preferred districts and radius."


def _value(c: CompanyFacts, t: TenderFacts) -> tuple[float, str]:
    v = t.estimated_value_paise
    if v is None:
        return 0.3, "Estimated value not stated."
    lo, hi = c.min_value_paise, c.max_value_paise
    if lo is None and hi is None:
        return 0.5, "No value range set in preferences."
    if lo is not None and v < lo:
        return _clamp(0.5 * v / lo), f"{format_inr(v)} is below your minimum of {format_inr(lo)}."
    if hi is not None and v > hi:
        return _clamp(0.5 * hi / v), f"{format_inr(v)} is above your maximum of {format_inr(hi)}."
    return 1.0, f"{format_inr(v)} is inside your preferred range."


def _experience(c: CompanyFacts, t: TenderFacts) -> tuple[float, str]:
    if not c.experiences:
        return 0.0, "No completed projects recorded."
    v = t.estimated_value_paise
    same = sorted(
        (e.value_paise for e in c.experiences if e.category_code == t.category_code), reverse=True
    )
    related_codes = RELATED.get(t.category_code or "", frozenset())
    related = sorted(
        (e.value_paise for e in c.experiences if e.category_code in related_codes), reverse=True
    )
    if not same and not related:
        return 0.0, "No completed projects in this or related categories."
    pool, factor, kind = (same, 1.0, "similar") if same else (related, 0.5, "related")
    if not v:
        return 0.6 * factor, f"{len(pool)} {kind} project(s); tender value unknown."
    # CPWD-style yardstick: one work ≥ 80%, two ≥ 60% or three ≥ 40% of the estimate.
    ratios = [
        pool[0] / (0.8 * v),
        pool[1] / (0.6 * v) if len(pool) > 1 else 0.0,
        pool[2] / (0.4 * v) if len(pool) > 2 else 0.0,
    ]
    fraction = _clamp(max(ratios)) * factor
    return fraction, f"Largest {kind} project {format_inr(pool[0])} vs estimate {format_inr(v)}."


def _capacity(c: CompanyFacts, t: TenderFacts) -> tuple[float, str]:
    parts: list[float] = []
    reasons: list[str] = []
    if c.max_concurrent_projects:
        active = c.current_active_projects or 0
        headroom = _clamp((c.max_concurrent_projects - active) / c.max_concurrent_projects)
        parts.append(headroom)
        reasons.append(f"{active}/{c.max_concurrent_projects} concurrent projects in hand")
    if c.annual_turnover_paise and t.estimated_value_paise:
        annualised = t.estimated_value_paise
        if t.completion_period_days and t.completion_period_days > 0:
            annualised = int(t.estimated_value_paise * 365 / max(t.completion_period_days, 90))
        ratio = annualised / c.annual_turnover_paise
        parts.append(1.0 if ratio <= 0.5 else _clamp(1.5 - ratio))
        reasons.append(f"annualised value is {ratio:.0%} of turnover")
    if not parts:
        return 0.3, "Capacity and turnover not recorded."
    return sum(parts) / len(parts), "; ".join(reasons).capitalize() + "."


def _time(t: TenderFacts, now: datetime) -> tuple[float, str]:
    if t.deadline is None:
        return 0.3, "Submission deadline not stated."
    days = (t.deadline - now).total_seconds() / 86400
    if days <= 0:
        return 0.0, "Submission deadline has passed."
    if days >= 14:
        return 1.0, f"{days:.0f} days to prepare."
    if days >= 7:
        return 0.7, f"{days:.0f} days to prepare."
    if days >= 3:
        return 0.4, f"Only {days:.0f} days to prepare."
    if days >= 1:
        return 0.15, f"Only {days:.1f} days to prepare."
    return 0.05, f"Under {days * 24:.0f} hours to prepare."


def score(c: CompanyFacts, t: TenderFacts, now: datetime | None = None) -> tuple[float, list[dict[str, Any]]]:
    now = now or utcnow()
    raw = {
        "specialization": _specialization(c, t),
        "location": _location(c, t),
        "value": _value(c, t),
        "experience": _experience(c, t),
        "capacity": _capacity(c, t),
        "time": _time(t, now),
    }
    factors = []
    for key, (fraction, reason) in raw.items():
        fraction = round(_clamp(fraction), 4)
        factors.append(
            Factor(key, LABELS[key], WEIGHTS[key], fraction, round(WEIGHTS[key] * fraction, 2), reason)
        )
    total = round(sum(f.points for f in factors), 2)
    return total, [asdict(f) for f in factors]
