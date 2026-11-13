#!/usr/bin/env python3
"""Background worker: reservation expiry, demo matching, and gated ML training.

Run separately from the API: python scripts/worker.py
Use one worker for ML jobs; multiple workers are safe for expiry/matching via row locks.
"""
from __future__ import annotations
import logging
from pathlib import Path
import sys
import time
from datetime import timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select
from app.core.config import get_settings
from app.db import session_scope
from app.models import TrainingJob, utcnow
from app.services import orders, trips

logging.basicConfig(level=get_settings().log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("routenex.worker")


def process_training():
    with session_scope() as db:
        # Recover jobs orphaned by a worker crash.
        for stale in db.scalars(select(TrainingJob).where(TrainingJob.status == "running", TrainingJob.started_at < utcnow() - timedelta(hours=1))):
            stale.status, stale.error = "queued", "Recovered after worker timeout"
        job = db.scalar(select(TrainingJob).where(TrainingJob.status == "queued").order_by(TrainingJob.id).with_for_update(skip_locked=True).limit(1))
        if not job:
            return
        job.status, job.started_at = "running", utcnow()
        job_id, params = job.id, dict(job.params)
    try:
        from ml import train
        report = train.run(get_settings().ml_artifact_dir, n_eta=params["eta_rows"], n_delay=params["delay_rows"], days=params["days"], log=log.info)
        with session_scope() as db:
            job = db.get(TrainingJob, job_id)
            job.status, job.report, job.finished_at = "completed", report, utcnow()
    except Exception as exc:
        log.exception("Training job %s failed", job_id)
        with session_scope() as db:
            job = db.get(TrainingJob, job_id)
            job.status, job.error, job.finished_at = "failed", str(exc)[:2000], utcnow()


def main():
    log.info("RouteNex worker started (demo_mode=%s)", get_settings().demo_mode)
    while True:
        try:
            with session_scope() as db:
                orders.tick(db)
                trips.tick(db)
            process_training()
        except Exception:
            log.exception("Worker iteration failed; retrying")
        time.sleep(10)


if __name__ == "__main__":
    main()
