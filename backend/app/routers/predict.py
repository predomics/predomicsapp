"""Prediction API — serve trained models as live prediction endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import pandas as pd

from ..core.database import get_db
from ..core.deps import get_current_user
from ..models.db_models import User, Job
import asyncio

from ..services import results_io
from ..services.prediction import predict_from_model, UnsupportedModelError

router = APIRouter(prefix="/predict", tags=["predict"])


class PredictRequest(BaseModel):
    """JSON body for prediction requests."""
    features: dict[str, list[float]]  # {feature_name: [values per sample]}
    sample_names: Optional[list[str]] = None


class PredictResponse(BaseModel):
    sample_names: list[str]
    scores: list[Optional[float]]  # None when a score is not finite
    predicted_classes: list[int]
    threshold: float
    matched_features: list[str]
    missing_features: list[str]
    n_samples: int


@router.post("/{job_id}", response_model=PredictResponse)
async def predict(
    job_id: str,
    body: PredictRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Score samples using a trained model (requires access to the job's project).

    Send a JSON body with feature values and receive class predictions.
    Authentication via Bearer token or X-API-Key header.
    """
    # Find the job and verify user has access to its project
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")

    # Verify project access
    from ..core.deps import get_project_access
    await get_project_access(job.project_id, user, db, require_role="viewer")

    results = await results_io.aload_results(job.project_id, job_id)
    if not results:
        raise HTTPException(status_code=404, detail="Results not found")

    # Build DataFrame from JSON features dict
    try:
        df = pd.DataFrame(body.features)
        if body.sample_names:
            if len(body.sample_names) != len(df):
                raise ValueError(
                    f"sample_names length ({len(body.sample_names)}) != "
                    f"feature values length ({len(df)})"
                )
            df.index = body.sample_names
        else:
            df.index = [f"sample_{i}" for i in range(len(df))]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid features data: {e}")

    try:
        prediction = await asyncio.to_thread(
            predict_from_model, results, df, None, False,
        )
    except UnsupportedModelError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {e}")

    return PredictResponse(**{k: prediction[k] for k in PredictResponse.model_fields})
