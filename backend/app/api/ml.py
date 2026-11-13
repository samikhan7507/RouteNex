from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_roles
from app.db import get_db
from app.models import TrainingJob, User
from app.schemas import TrainingInput
from app.services import mlserve
from app.services.common import audit

router = APIRouter(prefix="/api/ml", tags=["forecasting"])


@router.get("/status")
def status(user: User = Depends(require_roles("dispatcher", "fleet_manager", "admin")), db: Session = Depends(get_db)):
    jobs = db.scalars(select(TrainingJob).order_by(TrainingJob.id.desc()).limit(5)).all()
    return {**mlserve.status(), "jobs": [{"id": j.id, "status": j.status, "params": j.params,
            "error": j.error, "created_at": j.created_at, "finished_at": j.finished_at,
            "promoted": {n: m.get("promoted") for n, m in (j.report or {}).get("models", {}).items()}} for j in jobs]}


@router.get("/forecast")
def forecast(hours: int = Query(24, ge=2, le=48), user: User = Depends(require_roles("dispatcher", "fleet_manager", "admin"))):
    return mlserve.forecast(hours)


@router.post("/train", status_code=202)
def train(body: TrainingInput, user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    active = db.scalar(select(TrainingJob.id).where(TrainingJob.status.in_(["queued", "running"])).limit(1))
    if active:
        raise HTTPException(409, "A training job is already queued or running")
    job = TrainingJob(requested_by=user.id, params=body.model_dump())
    db.add(job)
    db.flush()
    audit(db, user, "ML_TRAIN_QUEUED", "training_job", job.id, body.model_dump())
    return {"job_id": job.id, "status": "queued", "note": "The background worker trains and promotes only models that pass validation gates"}


@router.get("/jobs/{job_id}")
def job(job_id: int, user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    j = db.get(TrainingJob, job_id)
    if not j:
        raise HTTPException(404, "Training job not found")
    return {"id": j.id, "status": j.status, "params": j.params, "report": j.report, "error": j.error,
            "created_at": j.created_at, "started_at": j.started_at, "finished_at": j.finished_at}
