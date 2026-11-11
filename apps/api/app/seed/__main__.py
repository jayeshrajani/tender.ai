"""Seed reference data, the source registry, DEMO tenders and two DEMO companies.

Usage: python -m app.seed [--reanchor-demo]
Idempotent: safe to run repeatedly.
"""

from __future__ import annotations

import argparse
import hashlib
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    Category,
    Certificate,
    CompanyDocument,
    CompanyExperience,
    CompanyPreference,
    Membership,
    NotificationPreference,
    Organization,
    Role,
    SourceProvider,
    Subcategory,
    User,
)
from app.security import hash_password
from app.seed.demo_tenders import cr, lakh
from app.seed.sources import SOURCES
from app.services import jobs, matching
from app.services.notifications import service as notify
from app.services.storage import get_storage, new_key
from app.services.taxonomy import CATEGORIES
from app.services.timeutil import today_ist, utcnow

DEMO_PASSWORD_NOTE = "Set via TENDEROS_DEMO_SEED_PASSWORD (local development only)."


def seed_taxonomy(db: Session) -> None:
    for i, c in enumerate(CATEGORIES):
        cat = db.scalar(select(Category).where(Category.code == c.code))
        if cat is None:
            cat = Category(code=c.code)
            db.add(cat)
        cat.name, cat.name_hi, cat.keywords, cat.sort_order = c.name, c.name_hi, list(c.keywords), i
        db.flush()
        for s in c.subs:
            sub = db.scalar(select(Subcategory).where(Subcategory.code == s.code))
            if sub is None:
                sub = Subcategory(code=s.code, category_id=cat.id)
                db.add(sub)
            sub.name, sub.keywords = s.name, list(s.keywords)


def seed_sources(db: Session, reanchor: bool) -> SourceProvider:
    for i, spec in enumerate(SOURCES):
        src = db.scalar(select(SourceProvider).where(SourceProvider.code == spec["code"]))
        if src is None:
            src = SourceProvider(code=spec["code"])
            db.add(src)
        protected = src.permission_status == "authorized"
        for k, v in spec.items():
            # Never overwrite an operator-recorded authorisation on re-seed.
            if protected and k in ("enabled", "configured", "permission_status"):
                continue
            setattr(src, k, v)
        src.sort_order = i
    db.flush()
    demo = db.scalar(select(SourceProvider).where(SourceProvider.code == "demo_fixture"))
    assert demo is not None
    cfg = dict(demo.config or {})
    if reanchor or "anchor_date" not in cfg:
        cfg["anchor_date"] = today_ist().isoformat()
    demo.config = cfg
    db.flush()
    return demo


def _placeholder_pdf(title: str) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 96), "DEMO PLACEHOLDER - NOT A REAL CERTIFICATE", fontsize=14)
    page.insert_text((72, 124), title, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def _doc(db: Session, org: Organization, title: str) -> CompanyDocument:
    data = _placeholder_pdf(title)
    key = new_key("company-docs", org.id, "pdf")
    get_storage().put(key, data, "application/pdf")
    d = CompanyDocument(
        organization_id=org.id, original_filename=f"{title[:60].replace('/', '-')}.pdf",
        content_type="application/pdf", size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
        storage_key=key,
    )
    db.add(d)
    db.flush()
    return d


def _cert(db: Session, org: Organization, cert_type: str, title: str, *, verified: bool, file: bool = True,
          expires: date | None = None, cls: str | None = None, value: int | None = None,
          number: str | None = None, issuer: str | None = None) -> Certificate:
    c = Certificate(
        organization_id=org.id, cert_type=cert_type, title=title, number=number, issuer=issuer,
        issued_on=(expires - timedelta(days=365 * 3)) if expires else None, expires_on=expires,
        registration_class=cls, value_paise=value,
        verification_status="verified" if verified else "unverified",
        document_id=_doc(db, org, title).id if file else None,
        notes="DEMO record",
    )
    db.add(c)
    db.flush()
    return c


def _user(db: Session, email: str, name: str) -> User:
    u = db.scalar(select(User).where(User.email == email))
    if u is None:
        u = User(email=email, full_name=name,
                 password_hash=hash_password(get_settings().demo_seed_password.get_secret_value()))
        db.add(u)
        db.flush()
    return u


def seed_company_narmada(db: Session) -> Organization | None:
    if db.scalar(select(Organization).where(Organization.legal_name == "Narmada Buildcon Pvt. Ltd. (DEMO)")):
        return None
    today = today_ist()
    org = Organization(
        legal_name="Narmada Buildcon Pvt. Ltd. (DEMO)", business_type="private_limited",
        gstin="23AAKCN4821M1Z6", pan="AAKCN4821M", contact_name="Rohit Verma (DEMO)",
        contact_email="owner@narmada.demo", contact_phone="+919800000001",
        address="DEMO address, MP Nagar Zone-II, Bhopal", base_district="Bhopal",
        annual_turnover_paise=cr("18.00"), turnover_financial_year="2025-26",
        contractor_registration_class="A", registration_authority="MP PWD centralised registration",
        workforce_count=145,
        equipment=["Hot mix plant 60–90 TPH", "Paver finisher", "Vibratory roller 8–10 T", "Motor grader",
                   "Batching plant 30 cum/hr", "Transit mixer ×4", "Excavator ×3", "Tipper ×8"],
        available_resources="Site engineers ×9, QC lab (mobile), 2 batching sites in Bhopal and Sehore.",
        max_concurrent_projects=6, current_active_projects=3, onboarding_step=6, is_demo=True,
    )
    db.add(org)
    db.flush()
    org.onboarding_completed_at = utcnow()
    db.add(CompanyPreference(
        organization_id=org.id, category_codes=["roads", "bridges", "drains", "rcc", "buildings"],
        subcategory_codes=["roads_bituminous", "roads_rural", "roads_widening", "drains_storm"],
        specialties=["bituminous", "PMGSY"], districts=["Bhopal", "Sehore", "Raisen", "Vidisha", "Narmadapuram"],
        operating_radius_km=150, statewide=False,
        min_tender_value_paise=lakh("50"), max_tender_value_paise=cr("15"),
    ))
    _cert(db, org, "gst", "GST registration certificate", verified=True, number="23AAKCN4821M1Z6", issuer="GSTN")
    _cert(db, org, "pan", "PAN card", verified=True, number="AAKCN4821M", issuer="Income Tax Department")
    _cert(db, org, "contractor_registration", "MP PWD contractor registration – Class A", verified=True,
          expires=today + timedelta(days=420), cls="A", number="PWD/REG/A/DEMO-1182", issuer="PWD Madhya Pradesh")
    _cert(db, org, "turnover_certificate", "CA-certified turnover FY 2023-26", verified=True,
          number="UDIN DEMO-24-118822", issuer="DEMO & Associates, Chartered Accountants")
    _cert(db, org, "solvency", "Bank solvency certificate", verified=False, value=cr("2.00"),
          expires=today + timedelta(days=150), issuer="DEMO Bank, Bhopal")
    _cert(db, org, "epf", "EPF establishment registration", verified=True, number="MPBHO0018822000")
    _cert(db, org, "labour_licence", "Labour licence (CLRA Act)", verified=True,
          expires=today - timedelta(days=41), number="LL/BPL/DEMO-778")
    roads1 = _cert(db, org, "experience", "Completion certificate – Raisen–Goharganj road", verified=True)
    roads2 = _cert(db, org, "experience", "Completion certificate – Sehore bypass resurfacing", verified=True)
    bridge = _cert(db, org, "experience", "Completion certificate – Parwati river minor bridge", verified=False)
    drain = _cert(db, org, "experience", "Completion certificate – Habibganj storm drain", verified=True)
    rcc = _cert(db, org, "experience", "Completion certificate – Kerwa retaining wall", verified=True)
    bldg = _cert(db, org, "experience", "Completion certificate – ITI hostel Vidisha", verified=False)
    for name, client, cat, dist, value, done, c in (
        ("Widening and BT of Raisen–Goharganj road (18 km)", "PWD Raisen", "roads", "Raisen", cr("6.80"), today - timedelta(days=400), roads1),
        ("Resurfacing of Sehore bypass", "PWD Sehore", "roads", "Sehore", cr("3.20"), today - timedelta(days=700), roads2),
        ("Minor bridge across Parwati river", "PWD Bridges Sehore", "bridges", "Sehore", cr("2.10"), today - timedelta(days=500), bridge),
        ("Storm water drain, Habibganj", "Bhopal Municipal Corporation", "drains", "Bhopal", cr("1.62"), today - timedelta(days=300), drain),
        ("RCC retaining wall, Kerwa dam approach", "WRD Bhopal", "rcc", "Bhopal", cr("2.40"), today - timedelta(days=900), rcc),
        ("ITI hostel building, Vidisha", "PWD PIU Vidisha", "buildings", "Vidisha", cr("4.00"), today - timedelta(days=200), bldg),
    ):
        db.add(CompanyExperience(organization_id=org.id, project_name=name, client_name=client, category_code=cat,
                                 district=dist, contract_value_paise=value, completed_on=done, certificate_id=c.id))
    owner = _user(db, "owner@narmada.demo", "Rohit Verma (DEMO)")
    analyst = _user(db, "analyst@narmada.demo", "Priya Sharma (DEMO)")
    viewer = _user(db, "viewer@narmada.demo", "Amit Jain (DEMO)")
    for u, role in ((owner, Role.owner), (analyst, Role.analyst), (viewer, Role.viewer)):
        db.add(Membership(organization_id=org.id, user_id=u.id, role=role))
    db.add(NotificationPreference(organization_id=org.id, user_id=owner.id, phone_e164="+919800000001",
                                  whatsapp_opt_in=True, opt_in_at=utcnow(), opt_in_source="demo_seed",
                                  min_relevance=45))
    db.add(NotificationPreference(organization_id=org.id, user_id=analyst.id))
    db.add(NotificationPreference(organization_id=org.id, user_id=viewer.id))
    db.flush()
    return org


def seed_company_malwa(db: Session) -> Organization | None:
    if db.scalar(select(Organization).where(Organization.legal_name == "Malwa Jal Infra LLP (DEMO)")):
        return None
    today = today_ist()
    org = Organization(
        legal_name="Malwa Jal Infra LLP (DEMO)", business_type="llp", gstin="23AAQFM7731K1Z2",
        pan="AAQFM7731K", contact_email="owner@malwa.demo", base_district="Indore",
        annual_turnover_paise=cr("32.00"), contractor_registration_class="A", workforce_count=210,
        max_concurrent_projects=5, current_active_projects=4, onboarding_step=6, is_demo=True,
    )
    db.add(org)
    db.flush()
    db.add(CompanyPreference(organization_id=org.id, category_codes=["water_supply", "sewerage"],
                             districts=["Indore", "Ujjain", "Dewas", "Shajapur", "Dhar"], operating_radius_km=200,
                             min_tender_value_paise=cr("5"), max_tender_value_paise=cr("60")))
    _cert(db, org, "gst", "GST registration certificate", verified=True)
    _cert(db, org, "contractor_registration", "PHED registration – Class A", verified=True,
          expires=today + timedelta(days=300), cls="A")
    _cert(db, org, "turnover_certificate", "CA-certified turnover", verified=True)
    exp = _cert(db, org, "experience", "Completion – Dewas sewer network", verified=True)
    db.add(CompanyExperience(organization_id=org.id, project_name="Sewer network, Dewas (AMRUT)", category_code="sewerage",
                             district="Dewas", contract_value_paise=cr("21.50"), completed_on=today - timedelta(days=380),
                             certificate_id=exp.id))
    owner = _user(db, "owner@malwa.demo", "Sunita Patidar (DEMO)")
    db.add(Membership(organization_id=org.id, user_id=owner.id, role=Role.owner))
    db.add(NotificationPreference(organization_id=org.id, user_id=owner.id))
    db.flush()
    return org


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reanchor-demo", action="store_true", help="Move DEMO tender dates to start today")
    args = parser.parse_args()
    with SessionLocal() as db:
        seed_taxonomy(db)
        demo = seed_sources(db, args.reanchor_demo)
        db.commit()
        key = f"seed-{demo.config['anchor_date']}"
        jobs.refresh_sources(db, key, trigger="manual")
        seed_company_narmada(db)
        seed_company_malwa(db)
        db.commit()
        stats = matching.recompute_all(db)
        db.commit()
        queued = 0
        for org in db.scalars(select(Organization.id)).all():
            queued += sum(notify.generate_event_alerts(db, org).values())
        notify.dispatch_pending(db)
        db.commit()
        print(f"Seed complete. Anchor {demo.config['anchor_date']}. Matching: {stats}. Alerts queued: {queued}.")
        print("DEMO logins: owner@narmada.demo / analyst@narmada.demo / viewer@narmada.demo / owner@malwa.demo")
        print(DEMO_PASSWORD_NOTE)


if __name__ == "__main__":
    main()
