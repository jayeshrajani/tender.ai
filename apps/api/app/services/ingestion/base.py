"""SourceAdapter interface and shared ingestion types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class SourceNotAuthorizedError(RuntimeError):
    """Raised when an adapter is asked to collect without authorisation/configuration."""


@dataclass
class DocumentRef:
    kind: str
    title: str
    source_url: str | None = None
    filename: str | None = None
    is_available: bool = False


@dataclass
class RequirementSpec:
    requirement_type: str
    label: str
    operator: str
    mandatory: bool = True
    threshold_value: int | None = None
    threshold_text: str | None = None
    unit: str | None = None
    period_years: int | None = None
    category_code: str | None = None
    document_ref: str | None = None
    page_number: int | None = None
    clause_ref: str | None = None
    evidence_quote: str | None = None
    extraction_method: str = "seed"
    verification_status: str = "source_verified"

    def fingerprint(self) -> tuple[Any, ...]:
        return (
            self.requirement_type,
            self.operator,
            self.mandatory,
            self.threshold_value,
            self.threshold_text,
            self.category_code,
            self.page_number,
        )


@dataclass
class NormalizedTender:
    source_tender_id: str
    title: str
    reference_number: str | None = None
    department: str | None = None
    issuing_organization: str | None = None
    district: str | None = None
    location: str | None = None
    category_code: str | None = None
    subcategory_codes: list[str] = field(default_factory=list)
    tender_type: str | None = None
    estimated_value_paise: int | None = None
    emd_paise: int | None = None
    tender_fee_paise: int | None = None
    completion_period_days: int | None = None
    published_at: datetime | None = None
    bid_submission_start_at: datetime | None = None
    bid_submission_end_at: datetime | None = None
    bid_opening_at: datetime | None = None
    pre_bid_meeting_at: datetime | None = None
    status: str = "active"
    nit_summary: str | None = None
    source_url: str | None = None
    source_organization: str | None = None
    documents: list[DocumentRef] = field(default_factory=list)
    requirements: list[RequirementSpec] | None = None


@dataclass
class ChangeRecord:
    """A corrigendum or update to apply on top of the original record."""

    reference: str
    changes: dict[str, Any]
    note: str | None = None
    kind: str = "corrigendum"


@dataclass
class AdapterHealth:
    enabled: bool
    configured: bool
    authorized: bool
    message: str


class SourceAdapter(ABC):
    code: str
    #: Whether the scheduler may pull from this adapter (manual adapters are push-only).
    pull_capable: bool = False

    @abstractmethod
    def health(self) -> AdapterHealth: ...

    @abstractmethod
    def discover(self, since: datetime | None) -> Iterable[str]:
        """Return source tender IDs that are new or changed since ``since``."""

    @abstractmethod
    def fetch_metadata(self, source_tender_id: str) -> NormalizedTender: ...

    @abstractmethod
    def fetch_documents(self, source_tender_id: str) -> list[DocumentRef]: ...

    @abstractmethod
    def fetch_changes(self, source_tender_id: str) -> list[ChangeRecord]: ...
