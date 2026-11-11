"""SQLAlchemy models.

Conventions: UUID primary keys, timestamptz in UTC, money as BIGINT paise, and every
company-owned table carries a non-null ``organization_id``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    type_annotation_map = {
        uuid.UUID: UUID(as_uuid=True),
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSONB,
        list[str]: ARRAY(String),
    }


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


def _created() -> Mapped[datetime]:
    return mapped_column(server_default=func.now(), nullable=False)


def _updated() -> Mapped[datetime]:
    return mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)


def _org_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)


# ---------------------------------------------------------------------------
# Enumerations (stored as short strings)
# ---------------------------------------------------------------------------


class Role(StrEnum):
    owner = "owner"
    admin = "admin"
    analyst = "analyst"
    viewer = "viewer"


class PermissionStatus(StrEnum):
    demo = "not_required_demo"
    operator_attested = "operator_attested"
    pending_authorization = "pending_authorization"
    authorized = "authorized"
    link_only = "link_only"


class CollectionMode(StrEnum):
    demo = "demo_fixture"
    manual_csv = "manual_csv_import"
    manual_document = "manual_document_import"
    official_feed = "official_feed"
    public_homepage = "public_homepage_summary"
    link_only = "link_only"


class RequirementResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"


class VerificationStatus(StrEnum):
    unverified = "unverified"
    verified = "verified"
    rejected = "rejected"


class RequirementReview(StrEnum):
    source_verified = "source_verified"
    needs_review = "needs_review"
    rejected = "rejected"


# ---------------------------------------------------------------------------
# Identity & tenancy
# ---------------------------------------------------------------------------


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    legal_name: Mapped[str] = mapped_column(String(200))
    business_type: Mapped[str | None] = mapped_column(String(40))
    gstin: Mapped[str | None] = mapped_column(String(15))
    pan: Mapped[str | None] = mapped_column(String(10))
    contact_name: Mapped[str | None] = mapped_column(String(120))
    contact_email: Mapped[str | None] = mapped_column(String(254))
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    base_district: Mapped[str | None] = mapped_column(String(60))

    annual_turnover_paise: Mapped[int | None] = mapped_column(BigInteger)
    turnover_financial_year: Mapped[str | None] = mapped_column(String(9))
    contractor_registration_class: Mapped[str | None] = mapped_column(String(10))
    registration_authority: Mapped[str | None] = mapped_column(String(120))
    workforce_count: Mapped[int | None] = mapped_column(Integer)
    equipment: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default="{}")
    available_resources: Mapped[str | None] = mapped_column(Text)
    max_concurrent_projects: Mapped[int | None] = mapped_column(Integer)
    current_active_projects: Mapped[int | None] = mapped_column(Integer)

    onboarding_step: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    onboarding_completed_at: Mapped[datetime | None]
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(254), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    last_login_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = _created()


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = _created()

    user: Mapped[User] = relationship(lazy="joined")
    organization: Mapped[Organization] = relationship(lazy="joined")


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    email: Mapped[str] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime]
    accepted_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = _created()


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Server-side active tenant; the client never supplies a company id.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime]
    created_at: Mapped[datetime] = _created()
    last_seen_at: Mapped[datetime] = _created()


# ---------------------------------------------------------------------------
# Taxonomy & company profile
# ---------------------------------------------------------------------------


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    name_hi: Mapped[str | None] = mapped_column(String(80))
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default="{}")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    subcategories: Mapped[list[Subcategory]] = relationship(
        back_populates="category", order_by="Subcategory.name", lazy="selectin"
    )


class Subcategory(Base):
    __tablename__ = "subcategories"

    id: Mapped[uuid.UUID] = _uuid_pk()
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(48), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default="{}")

    category: Mapped[Category] = relationship(back_populates="subcategories")


class CompanyPreference(Base):
    __tablename__ = "company_preferences"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), unique=True
    )
    category_codes: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default="{}")
    subcategory_codes: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, server_default="{}"
    )
    specialties: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default="{}")
    districts: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default="{}")
    operating_radius_km: Mapped[int | None] = mapped_column(Integer)
    statewide: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    min_tender_value_paise: Mapped[int | None] = mapped_column(BigInteger)
    max_tender_value_paise: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = _updated()


class CompanyDocument(Base):
    __tablename__ = "company_documents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(300))
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _created()


class Certificate(Base):
    __tablename__ = "certificates"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    cert_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(160))
    number: Mapped[str | None] = mapped_column(String(80))
    issuer: Mapped[str | None] = mapped_column(String(160))
    issued_on: Mapped[date | None] = mapped_column(Date)
    expires_on: Mapped[date | None] = mapped_column(Date)
    registration_class: Mapped[str | None] = mapped_column(String(10))
    value_paise: Mapped[int | None] = mapped_column(BigInteger)
    verification_status: Mapped[str] = mapped_column(
        String(16), default=VerificationStatus.unverified, server_default="unverified"
    )
    verified_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    verified_at: Mapped[datetime | None]
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("company_documents.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    document: Mapped[CompanyDocument | None] = relationship(lazy="joined")


class CompanyExperience(Base):
    __tablename__ = "company_experience"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    project_name: Mapped[str] = mapped_column(String(240))
    client_name: Mapped[str | None] = mapped_column(String(160))
    category_code: Mapped[str] = mapped_column(String(32))
    district: Mapped[str | None] = mapped_column(String(60))
    contract_value_paise: Mapped[int] = mapped_column(BigInteger)
    completed_on: Mapped[date | None] = mapped_column(Date)
    certificate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("certificates.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _created()

    certificate: Mapped[Certificate | None] = relationship(lazy="joined")


# ---------------------------------------------------------------------------
# Sources & ingestion
# ---------------------------------------------------------------------------


class SourceProvider(Base):
    __tablename__ = "source_providers"

    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(48), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    owner_organization: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(40))
    url: Mapped[str | None] = mapped_column(Text)
    api_status: Mapped[str] = mapped_column(String(120))
    collection_mode: Mapped[str] = mapped_column(String(32))
    permission_status: Mapped[str] = mapped_column(String(32))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    configured: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    captcha_dependency: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    coverage_note: Mapped[str] = mapped_column(Text)
    phase: Mapped[str] = mapped_column(String(8), default="V1")
    priority: Mapped[str] = mapped_column(String(4), default="P1")
    adapter: Mapped[str | None] = mapped_column(String(48))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    last_success_at: Mapped[datetime | None]
    last_failure_at: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class SourceRun(Base):
    __tablename__ = "source_runs"
    __table_args__ = (
        UniqueConstraint("source_id", "slot_key", name="uq_source_runs_slot"),
        Index("ix_source_runs_source_started", "source_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_providers.id", ondelete="CASCADE"))
    # Imports are tenant-scoped; scheduled global runs have no organization.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    trigger: Mapped[str] = mapped_column(String(16))  # scheduled | manual | import
    slot_key: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16))  # running|succeeded|partial|failed|skipped
    attempt: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    started_at: Mapped[datetime] = _created()
    finished_at: Mapped[datetime | None]
    records_seen: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    records_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    records_updated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    records_unchanged: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    duplicates: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed_records: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    message: Mapped[str | None] = mapped_column(Text)
    operator_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    filename: Mapped[str | None] = mapped_column(String(255))
    file_sha256: Mapped[str | None] = mapped_column(String(64))

    source: Mapped[SourceProvider] = relationship(lazy="joined")


class JobRun(Base):
    """Scheduler slots. The unique (job, slot_key) makes every scheduled job idempotent."""

    __tablename__ = "job_runs"
    __table_args__ = (UniqueConstraint("job", "slot_key"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    job: Mapped[str] = mapped_column(String(40))
    slot_key: Mapped[str] = mapped_column(String(40))
    trigger: Mapped[str] = mapped_column(String(16), default="scheduled")
    status: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = _created()
    finished_at: Mapped[datetime | None]
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    error: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Tenders
# ---------------------------------------------------------------------------


class Tender(Base):
    __tablename__ = "tenders"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "source_tender_id",
            "visibility_org_id",
            name="uq_tenders_source_identity",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_tenders_deadline", "bid_submission_end_at"),
        Index("ix_tenders_value", "estimated_value_paise"),
        Index("ix_tenders_district", "district"),
        Index("ix_tenders_category", "category_code"),
        Index("ix_tenders_dedupe_key", "dedupe_key"),
        Index("ix_tenders_visibility", "visibility_org_id"),
        Index(
            "ix_tenders_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_providers.id"))
    source_tender_id: Mapped[str] = mapped_column(String(120))
    reference_number: Mapped[str | None] = mapped_column(String(160))
    title: Mapped[str] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(String(200))
    issuing_organization: Mapped[str | None] = mapped_column(String(200))
    district: Mapped[str | None] = mapped_column(String(60))
    location: Mapped[str | None] = mapped_column(String(200))
    category_code: Mapped[str | None] = mapped_column(String(32))
    subcategory_codes: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default="{}")
    tender_type: Mapped[str | None] = mapped_column(String(60))
    estimated_value_paise: Mapped[int | None] = mapped_column(BigInteger)
    emd_paise: Mapped[int | None] = mapped_column(BigInteger)
    tender_fee_paise: Mapped[int | None] = mapped_column(BigInteger)
    completion_period_days: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[datetime | None]
    bid_submission_start_at: Mapped[datetime | None]
    bid_submission_end_at: Mapped[datetime | None]
    bid_opening_at: Mapped[datetime | None]
    pre_bid_meeting_at: Mapped[datetime | None]
    previous_deadline_at: Mapped[datetime | None]
    deadline_changed_at: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    nit_summary: Mapped[str | None] = mapped_column(Text)
    documents_available: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # Provenance
    source_url: Mapped[str | None] = mapped_column(Text)
    source_organization: Mapped[str | None] = mapped_column(String(200))
    retrieval_method: Mapped[str] = mapped_column(String(32))
    imported_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    imported_at: Mapped[datetime] = _created()
    permission_status: Mapped[str] = mapped_column(String(32))
    original_file_sha256: Mapped[str | None] = mapped_column(String(64))
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_runs.id", ondelete="SET NULL")
    )
    # NULL = globally visible (demo / authorised feed). Set = private to the importing company.
    visibility_org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    content_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    dedupe_key: Mapped[str | None] = mapped_column(String(200))
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenders.id", ondelete="SET NULL")
    )
    last_seen_at: Mapped[datetime] = _created()
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    source: Mapped[SourceProvider] = relationship(lazy="joined")
    requirements: Mapped[list[TenderRequirement]] = relationship(
        back_populates="tender", lazy="selectin", order_by="TenderRequirement.sort_order"
    )
    documents: Mapped[list[TenderDocument]] = relationship(
        back_populates="tender", lazy="selectin", order_by="TenderDocument.created_at"
    )


class TenderVersion(Base):
    __tablename__ = "tender_versions"
    __table_args__ = (UniqueConstraint("tender_id", "version"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    tender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    change_kind: Mapped[str] = mapped_column(String(16))  # initial | update | corrigendum
    changed_fields: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default="{}")
    previous_values: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    corrigendum_ref: Mapped[str | None] = mapped_column(String(160))
    note: Mapped[str | None] = mapped_column(Text)
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_runs.id", ondelete="SET NULL")
    )
    captured_at: Mapped[datetime] = _created()


class TenderDocument(Base):
    __tablename__ = "tender_documents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))  # nit | boq | corrigendum | drawing | other
    title: Mapped[str] = mapped_column(String(240))
    filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(80))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    storage_key: Mapped[str | None] = mapped_column(String(300))
    source_url: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    is_available: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    extracted_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    retrieval_method: Mapped[str] = mapped_column(String(32))
    permission_status: Mapped[str] = mapped_column(String(32))
    imported_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = _created()

    tender: Mapped[Tender] = relationship(back_populates="documents")


class TenderRequirement(Base):
    __tablename__ = "tender_requirements"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), index=True)
    requirement_type: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(240))
    mandatory: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    operator: Mapped[str] = mapped_column(String(8))  # gte | lte | eq | exists | info
    threshold_value: Mapped[int | None] = mapped_column(BigInteger)
    threshold_text: Mapped[str | None] = mapped_column(String(120))
    unit: Mapped[str | None] = mapped_column(String(16))  # paise | count | years | class | none
    period_years: Mapped[int | None] = mapped_column(Integer)
    category_code: Mapped[str | None] = mapped_column(String(32))
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tender_documents.id", ondelete="SET NULL")
    )
    document_ref: Mapped[str | None] = mapped_column(String(200))
    page_number: Mapped[int | None] = mapped_column(Integer)
    clause_ref: Mapped[str | None] = mapped_column(String(60))
    evidence_quote: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(24))  # seed | deterministic | ai | human
    verification_status: Mapped[str] = mapped_column(String(20))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = _created()

    tender: Mapped[Tender] = relationship(back_populates="requirements")


# ---------------------------------------------------------------------------
# Company × tender
# ---------------------------------------------------------------------------


class CompanyTenderMatch(Base):
    __tablename__ = "company_tender_matches"
    __table_args__ = (
        UniqueConstraint("organization_id", "tender_id"),
        Index("ix_matches_org_score", "organization_id", "relevance_score"),
        Index("ix_matches_org_status", "organization_id", "eligibility_status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    tender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), index=True)
    eligibility_status: Mapped[str] = mapped_column(String(20))
    eligibility_summary: Mapped[str] = mapped_column(Text)
    mandatory_failures: Mapped[int] = mapped_column(Integer, default=0)
    unknown_count: Mapped[int] = mapped_column(Integer, default=0)
    relevance_score: Mapped[float] = mapped_column(Numeric(5, 2))
    score_breakdown: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    tender_version: Mapped[int] = mapped_column(Integer)
    inputs_hash: Mapped[str] = mapped_column(String(64))
    computed_at: Mapped[datetime] = _created()


class CompanyRequirementEvaluation(Base):
    __tablename__ = "company_requirement_evaluations"
    __table_args__ = (UniqueConstraint("organization_id", "requirement_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    match_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("company_tender_matches.id", ondelete="CASCADE"), index=True
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tender_requirements.id", ondelete="CASCADE")
    )
    result: Mapped[str] = mapped_column(String(16))
    explanation: Mapped[str] = mapped_column(Text)
    company_evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    computed_at: Mapped[datetime] = _created()


class SavedTender(Base):
    __tablename__ = "saved_tenders"
    __table_args__ = (UniqueConstraint("organization_id", "tender_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    tender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    state: Mapped[str] = mapped_column(String(12))  # saved | dismissed
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = _updated()


class SavedView(Base):
    __tablename__ = "saved_views"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    query: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = _created()


class ReviewNote(Base):
    __tablename__ = "review_notes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    tender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()

    author: Mapped[User | None] = relationship(lazy="joined")


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    phone_e164: Mapped[str | None] = mapped_column(String(16))
    phone_verified_at: Mapped[datetime | None]
    whatsapp_opt_in: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    opt_in_at: Mapped[datetime | None]
    opt_in_source: Mapped[str | None] = mapped_column(String(40))
    opted_out_at: Mapped[datetime | None]
    daily_digest: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    urgent_alerts: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    closing_reminders: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    min_relevance: Mapped[int] = mapped_column(Integer, default=50, server_default="50")
    include_needs_verification: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    quiet_hours_start: Mapped[time | None] = mapped_column(Time)
    quiet_hours_end: Mapped[time | None] = mapped_column(Time)
    updated_at: Mapped[datetime] = _updated()


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (UniqueConstraint("dedupe_key"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    tender_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenders.id", ondelete="SET NULL"))
    alert_type: Mapped[str] = mapped_column(String(24))  # daily_digest|deadline_change|closing_48h|test
    dedupe_key: Mapped[str] = mapped_column(String(200))
    channel: Mapped[str] = mapped_column(String(16), default="whatsapp")
    template_name: Mapped[str] = mapped_column(String(80))
    recipient_masked: Mapped[str | None] = mapped_column(String(20))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    rendered_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    transport: Mapped[str] = mapped_column(String(16))  # simulated | meta
    scheduled_for: Mapped[datetime] = _created()
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sent_at: Mapped[datetime | None]
    provider_message_id: Mapped[str | None] = mapped_column(String(120), index=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (UniqueConstraint("provider_message_id", "status"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    outbox_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("notification_outbox.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    provider_message_id: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20))
    occurred_at: Mapped[datetime]
    error_code: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = _created()


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_org_created", "organization_id", "created_at"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = _created()

    actor: Mapped[User | None] = relationship(lazy="joined")
