"""Per-user model registry: joblib file per (user, target, version) + an ml_models row with
its features, metrics and training size. Older versions beyond MODEL_VERSIONS_KEPT are
removed (row and file)."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import joblib
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.ml.predict import Trained
from app.models import MLModel

log = logging.getLogger("twin.store")


def _dir(user_id: uuid.UUID) -> Path:
    d = Path(settings.model_store_dir) / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _jsonable(metrics: dict) -> dict:
    out = {}
    for k, v in metrics.items():
        if isinstance(v, float) and v != v:  # NaN
            out[k] = None
        elif isinstance(v, dict):
            out[k] = _jsonable(v)
        else:
            out[k] = v
    return out


def save(db: Session, user_id: uuid.UUID, t: Trained) -> MLModel:
    version = (
        db.scalar(
            select(func.max(MLModel.version)).where(
                MLModel.user_id == user_id, MLModel.target == t.target
            )
        )
        or 0
    ) + 1
    path = None
    if t.model is not None:
        path = str(_dir(user_id) / f"{t.target}-v{version}.joblib")
        joblib.dump(
            {
                "model": t.model,
                "features": t.features,
                "kind": t.kind,
                "target": t.target,
                "background": t.background,
            },
            path,
            compress=3,
        )
    for old in db.scalars(
        select(MLModel).where(
            MLModel.user_id == user_id, MLModel.target == t.target, MLModel.active
        )
    ):
        old.active = False
    metrics = dict(t.metrics)
    if t.model is None:
        metrics["constant"] = t.constant
    row = MLModel(
        user_id=user_id,
        target=t.target,
        version=version,
        kind=t.kind,
        path=path,
        features=t.features,
        metrics=_jsonable(metrics),
        n_train=int(t.metrics.get("n_train", 0)),
        active=True,
    )
    db.add(row)
    db.flush()
    _prune(db, user_id, t.target)
    return row


def _prune(db: Session, user_id: uuid.UUID, target: str) -> None:
    rows = db.scalars(
        select(MLModel)
        .where(MLModel.user_id == user_id, MLModel.target == target)
        .order_by(MLModel.version.desc())
    ).all()
    for old in rows[settings.model_versions_kept :]:
        if old.path:
            try:
                Path(old.path).unlink(missing_ok=True)
            except OSError:
                log.warning("could not delete %s", old.path)
        db.delete(old)


def load_active(db: Session, user_id: uuid.UUID, target: str) -> Trained | None:
    row = db.scalar(
        select(MLModel).where(MLModel.user_id == user_id, MLModel.target == target, MLModel.active)
    )
    if row is None:
        return None
    if row.path is None:
        return Trained(
            target,
            row.kind,
            row.features,
            constant=row.metrics.get("constant"),
            metrics=row.metrics,
        )
    try:
        blob = joblib.load(row.path)
    except (OSError, EOFError):
        log.warning("model file missing for %s/%s", user_id, target)
        return None
    return Trained(
        target,
        row.kind,
        blob["features"],
        model=blob["model"],
        metrics=row.metrics,
        background=blob.get("background"),
    )


def delete_user_models(user_id: uuid.UUID) -> None:
    d = Path(settings.model_store_dir) / str(user_id)
    if d.exists():
        for p in d.glob("*.joblib"):
            p.unlink(missing_ok=True)
        d.rmdir()
