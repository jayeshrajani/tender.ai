"""TenderOS worker: runs the IST schedule using the API's domain services.

- Reanalysis at 00:00, 08:00, 16:00 IST (eligibility, matching, authorised source refresh, alerts)
- Daily digest at 09:00 IST
- Outbox dispatch tick every minute (quiet-hours releases, retries)

Each slot is claimed through a unique (job, slot_key) row, so running several workers or
restarting mid-slot never duplicates work. On start-up the most recent missed slot is run.
"""

from __future__ import annotations

import logging
import signal
import threading

from app.db import SessionLocal
from app.services import jobs
from app.services.notifications.service import dispatch_pending
from app.services.timeutil import (
    latest_digest_slot,
    latest_reanalysis_slot,
    next_digest_slot,
    next_reanalysis_slot,
    slot_key,
    utcnow,
)

log = logging.getLogger("tenderos.worker")
TICK_SECONDS = 60
_stop = threading.Event()


def tick() -> None:
    now = utcnow()
    with SessionLocal() as db:
        job = jobs.run_reanalysis(db, slot_key(latest_reanalysis_slot(now)))
        if job:
            log.info("reanalysis %s -> %s %s", job.slot_key, job.status, job.stats)
        digest_slot = latest_digest_slot(now)
        if digest_slot is not None:
            d = jobs.run_digest(db, slot_key(digest_slot))
            if d:
                log.info("digest %s -> %s %s", d.slot_key, d.status, d.stats)
        stats = dispatch_pending(db)
        db.commit()
        if any(stats.values()):
            log.info("dispatch %s", stats)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGTERM, lambda *_: _stop.set())
    signal.signal(signal.SIGINT, lambda *_: _stop.set())
    log.info("worker started; next reanalysis %s, next digest %s", next_reanalysis_slot(), next_digest_slot())
    while not _stop.is_set():
        try:
            tick()
        except Exception:
            log.exception("worker tick failed")
        _stop.wait(TICK_SECONDS)
    log.info("worker stopped")


if __name__ == "__main__":
    main()
