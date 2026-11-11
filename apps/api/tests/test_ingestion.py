from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import SourceProvider, SourceRun, Tender, TenderVersion
from app.services import jobs
from app.services.ingestion.adapters import DemoFixtureAdapter
from app.services.ingestion.base import NormalizedTender
from app.services.ingestion.csv_import import CSVImportRequest, import_csv, preview
from app.services.ingestion.pipeline import Provenance, run_pull_adapter


def _source(db: Session, code: str) -> SourceProvider:
    s = db.scalar(select(SourceProvider).where(SourceProvider.code == code))
    assert s is not None
    return s


def test_demo_ingestion_is_idempotent(db: Session) -> None:
    jobs.refresh_sources(db, "slot-a", trigger="manual")
    assert db.scalar(select(func.count()).select_from(Tender)) == 24
    assert db.scalar(select(func.count()).select_from(Tender).where(Tender.is_demo.is_(False))) == 0
    jobs.refresh_sources(db, "slot-b", trigger="manual")
    assert db.scalar(select(func.count()).select_from(Tender)) == 24
    run = db.scalar(
        select(SourceRun).where(SourceRun.slot_key == "slot-b", SourceRun.source_id == _source(db, "demo_fixture").id)
    )
    assert run is not None and run.records_unchanged == 24 and run.records_created == 0


def test_corrigendum_creates_new_version_with_previous_deadline(db: Session) -> None:
    jobs.refresh_sources(db, "slot-a", trigger="manual")
    t = db.scalar(select(Tender).where(Tender.source_tender_id == "DEMO-2026-017"))
    assert t is not None and t.version == 2
    assert t.previous_deadline_at is not None and t.bid_submission_end_at > t.previous_deadline_at
    versions = db.scalars(select(TenderVersion).where(TenderVersion.tender_id == t.id).order_by(TenderVersion.version)).all()
    assert [v.change_kind for v in versions] == ["initial", "corrigendum"]
    assert "bid_submission_end_at" in versions[1].changed_fields
    assert versions[1].corrigendum_ref == "CORR-1/2026"


def test_scheduler_slot_runs_once(seeded: Session) -> None:
    first = jobs.run_reanalysis(seeded, "2026-11-11T08:00+05:30")
    assert first is not None and first.status == "succeeded", first.error if first else None
    assert first.stats["matching"]["organizations"] == 2
    assert jobs.run_reanalysis(seeded, "2026-11-11T08:00+05:30") is None


def test_gated_sources_are_skipped_not_collected(db: Session) -> None:
    jobs.refresh_sources(db, "slot-a", trigger="manual")
    for code in ("official_feed_mp", "mp_public_homepage"):
        run = db.scalar(select(SourceRun).where(SourceRun.source_id == _source(db, code).id))
        assert run is not None and run.status == "skipped"
        assert "not authorised" in (run.message or "")
        assert db.scalar(select(func.count()).select_from(Tender).where(Tender.source_id == _source(db, code).id)) == 0


class _BrokenAdapter(DemoFixtureAdapter):
    def discover(self, since: datetime | None) -> Iterable[str]:
        raise ConnectionError("portal unreachable")


class _OneBadRecord(DemoFixtureAdapter):
    def fetch_metadata(self, source_tender_id: str) -> NormalizedTender:
        if source_tender_id == "DEMO-2026-003":
            raise ValueError("malformed record")
        return super().fetch_metadata(source_tender_id)


def _prov(run_id):  # type: ignore[no-untyped-def]
    return Provenance(retrieval_method="demo_fixture", permission_status="not_required_demo", is_demo=True, source_run_id=run_id)


def test_source_failure_is_recorded_after_retries(db: Session) -> None:
    src = _source(db, "demo_fixture")
    run = run_pull_adapter(db, src, _BrokenAdapter(), _prov, trigger="manual", slot_key="fail-1", max_attempts=3)
    db.commit()
    assert run.status == "failed" and run.attempt == 3
    assert src.last_failure_at is not None and "unreachable" in (src.last_error or "")
    assert db.scalar(select(func.count()).select_from(Tender)) == 0


def test_single_bad_record_gives_partial_run(db: Session) -> None:
    src = _source(db, "demo_fixture")
    run = run_pull_adapter(db, src, _OneBadRecord(), _prov, trigger="manual", slot_key="partial-1")
    db.commit()
    assert run.status == "partial"
    assert run.failed_records == 1 and run.records_created == 23
    assert run.errors[0]["record"] == "DEMO-2026-003"


CSV = (
    "Tender ID,Name of Work,Reference No,Department,District,Estimated Value,Bid Submission End Date\n"
    "2026_TEST_000001_1,CC road in Damoh ward 4,REF-1,PWD,Damoh,85 lakh,25-12-2026 17:00\n"
    "2026_TEST_000002_1,Storm drain Bhopal,DEMO/2026_BMC_422109_1,BMC,Bhopal,1.86 Cr,26-12-2026 17:00\n"
    "2026_TEST_000001_1,Duplicate row,REF-1,PWD,Damoh,85 lakh,25-12-2026 17:00\n"
    ",Missing id,REF-9,PWD,Sagar,1 Cr,26-12-2026 17:00\n"
    "2026_TEST_000003_1,Bad date row,REF-3,PWD,Sagar,1 Cr,someday\n"
)


def test_csv_preview_suggests_mapping() -> None:
    p = preview(CSV.encode())
    assert p["row_count"] == 5
    assert p["suggested_mapping"]["tender_id"] == "Tender ID"
    assert p["suggested_mapping"]["title"] == "Name of Work"
    assert p["suggested_mapping"]["bid_submission_end_at"] == "Bid Submission End Date"


def test_csv_import_validation_duplicates_and_cross_source_dedupe(seeded: Session) -> None:
    db = seeded
    from app.models import Organization, User

    org = db.scalar(select(Organization).where(Organization.legal_name.like("Narmada%")))
    user = db.scalar(select(User).where(User.email == "owner@narmada.demo"))
    assert org and user
    p = preview(CSV.encode())
    run = import_csv(
        db, _source(db, "manual_csv"),
        CSVImportRequest(CSV.encode(), "export.csv", "abc", p["suggested_mapping"], "https://mptenders.gov.in/", "MP eProcurement"),
        organization_id=org.id, user_id=user.id,
    )
    db.commit()
    assert run.status == "partial"
    assert run.records_created == 1  # Damoh row
    assert run.duplicates == 2  # in-file duplicate + cross-source duplicate of DEMO-2026-004
    assert run.failed_records == 2
    assert {e["row"] for e in run.errors} == {4, 5, 6}
    imported = db.scalar(select(Tender).where(Tender.source_tender_id == "2026_TEST_000002_1"))
    canonical = db.scalar(select(Tender).where(Tender.source_tender_id == "DEMO-2026-004"))
    assert imported and canonical and imported.duplicate_of_id == canonical.id
    # Provenance is preserved on the duplicate record.
    assert imported.retrieval_method == "manual_csv" and imported.imported_by_user_id == user.id
    assert imported.visibility_org_id == org.id and imported.permission_status == "operator_attested"
