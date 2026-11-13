import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, Certificate, Organization, Tender


def test_requires_auth_and_csrf_header(client_factory) -> None:  # type: ignore[no-untyped-def]
    c = client_factory()
    assert c.get("/api/v1/tenders").status_code == 401
    bare = client_factory()
    bare.headers.pop("X-Requested-With")
    r = bare.post("/api/v1/auth/login", json={"email": "owner@narmada.demo", "password": "x"})
    assert r.status_code == 403 and "CSRF" in r.text


def test_login_rejects_wrong_password(client_factory) -> None:  # type: ignore[no-untyped-def]
    r = client_factory().post("/api/v1/auth/login", json={"email": "owner@narmada.demo", "password": "wrong-password"})
    assert r.status_code == 401


def test_tender_list_search_filter_sort(client_factory) -> None:  # type: ignore[no-untyped-def]
    c = client_factory()
    c.login("owner@narmada.demo")
    r = c.get("/api/v1/tenders", params={"page_size": 100})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 23  # 24 DEMO minus the closed one (hidden by default)
    scores = [i["relevance_score"] for i in body["items"]]
    assert scores == sorted(scores, reverse=True)

    r = c.get("/api/v1/tenders", params={"district": ["Bhopal"], "sort": "deadline"})
    items = r.json()["items"]
    assert items and all(i["district"] == "Bhopal" for i in items)
    deadlines = [i["deadline"] for i in items]
    assert deadlines == sorted(deadlines)

    r = c.get("/api/v1/tenders", params={"q": "hostel"})
    assert [i["title"] for i in r.json()["items"]] == [
        "Construction of 100-seater girls hostel at Government Polytechnic College, Bhopal (G+3)"
    ]
    r = c.get("/api/v1/tenders", params={"eligibility": ["NOT_ELIGIBLE"], "page_size": 100})
    assert all(i["eligibility_status"] == "NOT_ELIGIBLE" and i["action"] == "not_eligible" for i in r.json()["items"])
    r = c.get("/api/v1/tenders", params={"action": ["closed"]})
    assert [i["status"] for i in r.json()["items"]] == ["closed"]
    # LIKE wildcards in user input are escaped.
    assert c.get("/api/v1/tenders", params={"q": "%"}).json()["total"] == 0


def test_tender_detail_has_evidence_and_breakdown(client_factory, seeded: Session) -> None:  # type: ignore[no-untyped-def]
    c = client_factory()
    c.login("analyst@narmada.demo")
    t = seeded.scalar(select(Tender).where(Tender.source_tender_id == "DEMO-2026-001"))
    d = c.get(f"/api/v1/tenders/{t.id}").json()
    assert d["eligibility"]["status"] == "NOT_ELIGIBLE"
    assert d["relevance"]["score"] > 70  # relevant, but must not be presented as eligible
    fail = [r for r in d["eligibility"]["requirements"] if r["result"] == "FAIL"]
    assert fail and fail[0]["citation"]["page"] == 4 and fail[0]["citation"]["quote"]
    assert len(d["relevance"]["breakdown"]) == 6
    assert d["is_demo"] is True and d["provenance"]["retrieval_method"] == "demo_fixture"


def test_cross_tenant_isolation(client_factory, seeded: Session) -> None:  # type: ignore[no-untyped-def]
    a = client_factory()
    a.login("owner@narmada.demo")
    csv = b"Tender ID,Title,Bid Submission End Date\nPRIV-1,Private Narmada import road,25-12-2026 17:00\n"
    r = a.post("/api/v1/ingestion/import", data={"kind": "csv", "attestation": "true"},
               files={"file": ("x.csv", csv, "text/csv")})
    assert r.status_code == 201, r.text
    private = seeded.scalar(select(Tender).where(Tender.source_tender_id == "PRIV-1"))
    narmada_cert = seeded.scalar(
        select(Certificate).join(Organization, Organization.id == Certificate.organization_id)
        .where(Organization.legal_name.like("Narmada%"), Certificate.document_id.is_not(None))
    )
    link = a.get(f"/api/v1/company/documents/{narmada_cert.document_id}/link").json()["url"]
    assert a.get(link).status_code == 200

    b = client_factory()
    me = b.login("owner@malwa.demo")
    assert me["active_company"]["name"].startswith("Malwa")
    assert b.get(f"/api/v1/tenders/{private.id}").status_code == 404
    assert all(i["id"] != str(private.id) for i in b.get("/api/v1/tenders", params={"page_size": 100}).json()["items"])
    assert b.get(f"/api/v1/company/documents/{narmada_cert.document_id}/link").status_code == 404
    assert b.patch(f"/api/v1/company/certificates/{narmada_cert.id}/verification",
                   json={"verification_status": "rejected"}).status_code == 404
    assert b.get(link).status_code == 403  # signed link bound to the other company
    # A forged company switch is refused.
    narmada_id = seeded.scalar(select(Organization.id).where(Organization.legal_name.like("Narmada%")))
    assert b.post("/api/v1/auth/switch-company", json={"organization_id": str(narmada_id)}).status_code == 403
    assert all(i["source_code"] != "manual_csv" for i in b.get("/api/v1/ingestion/runs").json()["items"])


def test_roles_are_enforced(client_factory, seeded: Session) -> None:  # type: ignore[no-untyped-def]
    v = client_factory()
    v.login("viewer@narmada.demo")
    t = seeded.scalar(select(Tender).where(Tender.source_tender_id == "DEMO-2026-002"))
    assert v.post(f"/api/v1/tenders/{t.id}/save", json={"state": "saved"}).status_code == 403
    assert v.put("/api/v1/company/profile", json={"legal_name": "Hacked"}).status_code == 403
    an = client_factory()
    an.login("analyst@narmada.demo")
    assert an.post(f"/api/v1/tenders/{t.id}/save", json={"state": "saved"}).json() == {"saved_state": "saved"}
    assert an.post("/api/v1/team/invitations", json={"email": "x@y.in", "role": "viewer"}).status_code == 403


def test_register_and_onboarding_persist(client_factory, seeded: Session) -> None:  # type: ignore[no-untyped-def]
    c = client_factory()
    r = c.post("/api/v1/auth/register", json={"email": "new@contractor.in", "password": "long-password-1",
                                               "full_name": "New Owner", "company_name": "New Infra"})
    assert r.status_code == 201 and r.json()["active_company"]["onboarding_step"] == 1
    bad = c.put("/api/v1/company/profile", json={"gstin": "123", "step": 1})
    assert bad.status_code == 422
    ok = c.put("/api/v1/company/profile", json={"gstin": "23abcde1234f1z5", "pan": "ABCDE1234F", "step": 2,
                                                  "business_type": "proprietorship"})
    assert ok.status_code == 200 and ok.json()["gstin"] == "23ABCDE1234F1Z5"
    c.put("/api/v1/company/profile", json={"category_codes": ["roads"], "districts": ["Bhopal"], "step": 3})
    c.put("/api/v1/company/profile", json={"min_tender_value_paise": 5_000_000_00, "max_tender_value_paise": 1_000_000_00})
    profile = c.get("/api/v1/company/profile").json()
    assert profile["onboarding_step"] == 3
    assert profile["category_codes"] == ["roads"] and profile["districts"] == ["Bhopal"]
    assert profile["min_tender_value_paise"] is None  # invalid range was rejected
    done = c.put("/api/v1/company/profile", json={"complete": True}).json()
    assert done["onboarding_completed_at"] is not None
    assert seeded.scalar(select(AuditEvent).where(AuditEvent.action == "company.profile_updated")) is not None


def test_upload_validation(client_factory) -> None:  # type: ignore[no-untyped-def]
    c = client_factory()
    c.login("owner@narmada.demo")
    form = {"cert_type": "epf", "title": "EPF"}
    fake = c.post("/api/v1/company/documents", data=form, files={"file": ("x.pdf", b"MZ\x90\x00 not a pdf", "application/pdf")})
    assert fake.status_code == 422 and "does not match" in fake.text
    exe = c.post("/api/v1/company/documents", data=form, files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert exe.status_code == 422
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    ok = c.post("/api/v1/company/documents", data={**form, "expires_on": "2027-03-31"}, files={"file": ("epf.png", png, "image/png")})
    assert ok.status_code == 201 and ok.json()["verification_status"] == "unverified"
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "x")
        z.writestr("xl/workbook.xml", "x")
        z.writestr("xl/vbaProject.bin", "macro")
    macro = c.post("/api/v1/ingestion/import", data={"kind": "boq", "attestation": "true"},
                   files={"file": ("boq.xlsx", buf.getvalue(), "application/octet-stream")})
    assert macro.status_code == 422 and "Macro" in macro.text


def test_import_requires_attestation(client_factory) -> None:  # type: ignore[no-untyped-def]
    c = client_factory()
    c.login("analyst@narmada.demo")
    r = c.post("/api/v1/ingestion/import", data={"kind": "csv"}, files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")})
    assert r.status_code == 422 and "attestation" in r.text


def test_sources_never_claim_live(client_factory) -> None:  # type: ignore[no-untyped-def]
    c = client_factory()
    c.login("viewer@narmada.demo")
    body = c.get("/api/v1/sources").json()
    states = {s["code"]: s["collection_state"] for s in body["items"]}
    assert states["official_feed_mp"].startswith("Disabled")
    assert states["mp_public_homepage"].startswith("Disabled")
    assert states["demo_fixture"] == "Demo data"
    text = str(body).lower()
    for banned in ("'live'", "synced", "all tenders"):
        assert banned not in text
    assert body["schedule"]["reanalysis_times_ist"] == ["00:00", "08:00", "16:00"]
    assert len(body["schedule"]["reanalysis_history"]) == 30
    assert all(len(s["history"]) == 30 for s in body["items"])
    allowed = {"up", "degraded", "down", "skipped", "none"}
    assert all(set(s["history"]) <= allowed for s in body["items"])
