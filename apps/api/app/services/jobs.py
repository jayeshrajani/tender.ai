"""Scheduled jobs. Idempotent: each (job, slot_key) row can only be claimed once."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import JobRun, Organization, PermissionStatus, SourceProvider
from app.services import matching
from app.services.ingestion.adapters import get_adapter
from app.services.ingestion.pipeline import Provenance, run_pull_adapter
from app.services.notifications import service as notify
from app.services.timeutil import utcnow

log = logging.getLogger(__name__)

REANALYSIS = "reanalysis"
DIGEST = "daily_digest"


def claim(db: Session, job: str, slot_key: str, trigger: str) -> JobRun | None:
    job_id = uuid.uuid4()
    res = db.execute(
        pg_insert(JobRun)
        .values(id=job_id, job=job, slot_key=slot_key, trigger=trigger, status="running", started_at=utcnow())
        .on_conflict_do_nothing(index_elements=["job", "slot_key"])
        .returning(JobRun.id)
    ).scalar()
    db.commit()
    return db.get(JobRun, job_id) if res is not None else None


def _finish(db: Session, run: JobRun, stats: dict[str, Any], error: str | None = None) -> None:
    run.status = "failed" if error else "succeeded"
    run.stats = stats
    run.error = error
    run.finished_at = utcnow()
    db.commit()


def refresh_sources(db: Session, slot_key: str, trigger: str) -> list[dict[str, Any]]:
    """Pull only from sources whose collection is enabled, configured and authorised."""
    results = []
    for source in db.scalars(select(SourceProvider).order_by(SourceProvider.sort_order)):
        adapter = get_adapter(source)
        if adapter is None or not adapter.pull_capable:
            continue
        is_demo = source.code == "demo_fixture"

        def prov(run_id: uuid.UUID, _demo: bool = is_demo, _s: SourceProvider = source) -> Provenance:
            return Provenance(
                retrieval_method="demo_fixture" if _demo else "official_feed",
                permission_status=PermissionStatus.demo if _demo else _s.permission_status,
                is_demo=_demo,
                source_run_id=run_id,
            )

        run = run_pull_adapter(db, source, adapter, prov, trigger=trigger, slot_key=slot_key)
        db.commit()
        results.append({"source": source.code, "status": run.status, "message": run.message})
    return results


def run_reanalysis(db: Session, slot_key: str, trigger: str = "scheduled") -> JobRun | None:
    job = claim(db, REANALYSIS, slot_key, trigger)
    if job is None:
        log.debug("reanalysis %s already claimed", slot_key)
        return None
    stats: dict[str, Any] = {}
    try:
        stats["sources"] = refresh_sources(db, slot_key, trigger)
        stats["matching"] = matching.recompute_all(db)
        db.commit()
        alerts = {"closing_48h": 0, "deadline_change": 0}
        for org_id in db.scalars(select(Organization.id)).all():
            for k, v in notify.generate_event_alerts(db, org_id).items():
                alerts[k] += v
        stats["alerts_queued"] = alerts
        stats["dispatch"] = notify.dispatch_pending(db)
        db.commit()
        _finish(db, job, stats)
    except Exception as exc:
        db.rollback()
        log.exception("reanalysis failed")
        job = db.get(JobRun, job.id)
        assert job is not None
        _finish(db, job, stats, error=str(exc)[:500])
    return job


def run_digest(db: Session, slot_key: str, trigger: str = "scheduled") -> JobRun | None:
    job = claim(db, DIGEST, slot_key, trigger)
    if job is None:
        return None
    stats: dict[str, Any] = {}
    try:
        queued = 0
        for org_id in db.scalars(select(Organization.id)).all():
            queued += notify.generate_digests(db, org_id)
        stats["digests_queued"] = queued
        stats["dispatch"] = notify.dispatch_pending(db)
        db.commit()
        _finish(db, job, stats)
    except Exception as exc:
        db.rollback()
        log.exception("digest failed")
        job = db.get(JobRun, job.id)
        assert job is not None
        _finish(db, job, stats, error=str(exc)[:500])
    return job
