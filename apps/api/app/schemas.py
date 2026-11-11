"""Request schemas (Pydantic v2). Responses are plain JSON built in routers."""

from __future__ import annotations

import re
from datetime import date, time
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.services.districts import MP_DISTRICTS
from app.services.taxonomy import CATEGORY_BY_CODE, CATEGORY_CODES

GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
PAN_RE = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")
PHONE_RE = re.compile(r"^\+91[6-9]\d{9}$")
REG_CLASSES = ("AA", "A", "B", "C", "D")
BUSINESS_TYPES = ("proprietorship", "partnership", "llp", "private_limited", "public_limited", "other")
CERT_TYPES = (
    "contractor_registration", "gst", "pan", "turnover_certificate", "solvency", "experience",
    "epf", "esic", "labour_licence", "electrical_licence", "udyam", "iso", "other",
)
Money = Field(default=None, ge=0, le=10**15)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    company_name: str = Field(min_length=2, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class SwitchCompanyIn(BaseModel):
    organization_id: str


class AcceptInviteIn(BaseModel):
    token: str = Field(min_length=20, max_length=100)
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    password: str | None = Field(default=None, min_length=10, max_length=128)


class ProfileIn(BaseModel):
    """Partial update; the onboarding wizard saves one step at a time."""

    step: int | None = Field(default=None, ge=1, le=6)
    complete: bool = False

    legal_name: str | None = Field(default=None, min_length=2, max_length=200)
    business_type: Literal[BUSINESS_TYPES] | None = None  # type: ignore[valid-type]
    gstin: str | None = None
    pan: str | None = None
    contact_name: str | None = Field(default=None, max_length=120)
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    address: str | None = Field(default=None, max_length=500)
    base_district: str | None = None

    category_codes: list[str] | None = None
    subcategory_codes: list[str] | None = None
    specialties: list[str] | None = Field(default=None, max_length=20)
    districts: list[str] | None = Field(default=None, max_length=55)
    operating_radius_km: int | None = Field(default=None, ge=0, le=1000)
    statewide: bool | None = None
    min_tender_value_paise: int | None = Money
    max_tender_value_paise: int | None = Money

    annual_turnover_paise: int | None = Money
    turnover_financial_year: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    contractor_registration_class: Literal[REG_CLASSES] | None = None  # type: ignore[valid-type]
    registration_authority: str | None = Field(default=None, max_length=120)
    workforce_count: int | None = Field(default=None, ge=0, le=100000)
    equipment: list[str] | None = Field(default=None, max_length=50)
    available_resources: str | None = Field(default=None, max_length=2000)
    max_concurrent_projects: int | None = Field(default=None, ge=0, le=500)
    current_active_projects: int | None = Field(default=None, ge=0, le=500)

    @field_validator("gstin", "pan", mode="before")
    @classmethod
    def _upper(cls, v: object) -> object:
        return v.strip().upper() if isinstance(v, str) and v.strip() else None

    @field_validator("gstin")
    @classmethod
    def _gstin(cls, v: str | None) -> str | None:
        if v and not GSTIN_RE.match(v):
            raise ValueError("GSTIN must be 15 characters, e.g. 23ABCDE1234F1Z5")
        return v

    @field_validator("pan")
    @classmethod
    def _pan(cls, v: str | None) -> str | None:
        if v and not PAN_RE.match(v):
            raise ValueError("PAN must look like ABCDE1234F")
        return v

    @field_validator("contact_phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        if v:
            v = re.sub(r"[\s-]", "", v)
            if not v.startswith("+"):
                v = "+91" + v[-10:]
            if not PHONE_RE.match(v):
                raise ValueError("Enter a 10-digit Indian mobile number")
        return v or None

    @field_validator("base_district")
    @classmethod
    def _district(cls, v: str | None) -> str | None:
        if v and v not in MP_DISTRICTS:
            raise ValueError("Unknown MP district")
        return v or None

    @field_validator("districts")
    @classmethod
    def _districts(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            bad = [d for d in v if d not in MP_DISTRICTS]
            if bad:
                raise ValueError(f"Unknown MP districts: {', '.join(bad)}")
        return v

    @field_validator("category_codes")
    @classmethod
    def _cats(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and any(c not in CATEGORY_CODES for c in v):
            raise ValueError("Unknown work category")
        return v

    @field_validator("specialties", "equipment")
    @classmethod
    def _strip_list(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return [s.strip()[:120] for s in v if s and s.strip()]

    @model_validator(mode="after")
    def _ranges(self) -> ProfileIn:
        lo, hi = self.min_tender_value_paise, self.max_tender_value_paise
        if lo is not None and hi is not None and lo > hi:
            raise ValueError("Minimum tender value cannot exceed maximum")
        if self.subcategory_codes is not None:
            valid = {s.code for c in CATEGORY_BY_CODE.values() for s in c.subs}
            if any(s not in valid for s in self.subcategory_codes):
                raise ValueError("Unknown subcategory")
        return self


class ExperienceIn(BaseModel):
    project_name: str = Field(min_length=3, max_length=240)
    client_name: str | None = Field(default=None, max_length=160)
    category_code: str
    district: str | None = None
    contract_value_paise: int = Field(gt=0, le=10**15)
    completed_on: date | None = None
    certificate_id: str | None = None

    @field_validator("category_code")
    @classmethod
    def _cat(cls, v: str) -> str:
        if v not in CATEGORY_CODES:
            raise ValueError("Unknown work category")
        return v


class CertificateIn(BaseModel):
    cert_type: Literal[CERT_TYPES]  # type: ignore[valid-type]
    title: str = Field(min_length=2, max_length=160)
    number: str | None = Field(default=None, max_length=80)
    issuer: str | None = Field(default=None, max_length=160)
    issued_on: date | None = None
    expires_on: date | None = None
    registration_class: Literal[REG_CLASSES] | None = None  # type: ignore[valid-type]
    value_paise: int | None = Money
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _dates(self) -> CertificateIn:
        if self.issued_on and self.expires_on and self.expires_on < self.issued_on:
            raise ValueError("Expiry date is before issue date")
        return self


class CertificateVerifyIn(BaseModel):
    verification_status: Literal["verified", "rejected", "unverified"]


class SaveTenderIn(BaseModel):
    state: Literal["saved", "dismissed", "none"]


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class RequirementReviewIn(BaseModel):
    verification_status: Literal["source_verified", "needs_review", "rejected"]
    mandatory: bool | None = None
    threshold_value: int | None = Field(default=None, ge=0, le=10**15)
    threshold_text: str | None = Field(default=None, max_length=120)


class SavedViewIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    query: str = Field(max_length=1000)


class NotificationPrefsIn(BaseModel):
    phone_e164: str | None = None
    whatsapp_opt_in: bool
    daily_digest: bool = True
    urgent_alerts: bool = True
    closing_reminders: bool = True
    min_relevance: int = Field(default=50, ge=0, le=100)
    include_needs_verification: bool = True
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None

    @field_validator("phone_e164")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        if v:
            v = re.sub(r"[\s-]", "", v)
            if not v.startswith("+"):
                v = "+91" + v[-10:]
            if not PHONE_RE.match(v):
                raise ValueError("Enter a 10-digit Indian mobile number")
        return v or None

    @model_validator(mode="after")
    def _optin_needs_phone(self) -> NotificationPrefsIn:
        if self.whatsapp_opt_in and not self.phone_e164:
            raise ValueError("A mobile number is required to opt in to WhatsApp alerts")
        return self


class InviteIn(BaseModel):
    email: EmailStr
    role: Literal["admin", "analyst", "viewer"]


class RoleChangeIn(BaseModel):
    role: Literal["owner", "admin", "analyst", "viewer"]
