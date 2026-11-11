"""Plain data snapshots consumed by the eligibility and relevance engines.

Keeping the engines free of ORM objects makes the rules deterministic and unit-testable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class CertFact:
    id: uuid.UUID
    cert_type: str
    title: str
    verification_status: str
    expires_on: date | None = None
    registration_class: str | None = None
    value_paise: int | None = None
    has_document: bool = False


@dataclass(frozen=True)
class ExperienceFact:
    id: uuid.UUID
    project_name: str
    category_code: str
    value_paise: int
    completed_on: date | None = None
    certificate: CertFact | None = None


@dataclass(frozen=True)
class CompanyFacts:
    organization_id: uuid.UUID
    gstin: str | None = None
    pan: str | None = None
    annual_turnover_paise: int | None = None
    registration_class: str | None = None
    certificates: tuple[CertFact, ...] = ()
    experiences: tuple[ExperienceFact, ...] = ()
    equipment: tuple[str, ...] = ()
    workforce_count: int | None = None
    max_concurrent_projects: int | None = None
    current_active_projects: int | None = None
    category_codes: tuple[str, ...] = ()
    subcategory_codes: tuple[str, ...] = ()
    specialties: tuple[str, ...] = ()
    districts: tuple[str, ...] = ()
    base_district: str | None = None
    operating_radius_km: int | None = None
    statewide: bool = False
    min_value_paise: int | None = None
    max_value_paise: int | None = None


@dataclass(frozen=True)
class RequirementFact:
    id: uuid.UUID
    requirement_type: str
    label: str
    mandatory: bool
    operator: str
    verification_status: str
    threshold_value: int | None = None
    threshold_text: str | None = None
    unit: str | None = None
    category_code: str | None = None


@dataclass(frozen=True)
class TenderFacts:
    id: uuid.UUID
    title: str
    category_code: str | None
    subcategory_codes: tuple[str, ...]
    district: str | None
    estimated_value_paise: int | None
    deadline: datetime | None
    completion_period_days: int | None = None
    requirements: tuple[RequirementFact, ...] = field(default_factory=tuple)
