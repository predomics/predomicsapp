"""Data exploration endpoints — feature statistics and filtering via Rust engine."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import get_current_user, get_project_with_access
from ..models.db_models import User, Project
from ..services import data_analysis

router = APIRouter(prefix="/data-explore", tags=["data-explore"])


def _resolve_train_files(project: Project) -> tuple[str, str, bool]:
    """Find xtrain and ytrain disk paths from project relationships.

    Returns (x_path, y_path, features_in_rows).
    The project must have been loaded with selectinload for dataset_links -> dataset -> files.
    """
    x_path = y_path = None
    for link in project.dataset_links:
        for f in link.dataset.files:
            if f.role == "xtrain":
                x_path = f.disk_path
            elif f.role == "ytrain":
                y_path = f.disk_path
    if not x_path or not y_path:
        raise HTTPException(
            status_code=404,
            detail="X train and/or y train files not found. Upload datasets first.",
        )
    return x_path, y_path


@router.get("/{project_id}/summary")
async def get_data_summary(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get basic data dimensions and class distribution (viewer access)."""
    project, _ = await get_project_with_access(project_id, user, db, require_role="viewer")
    x_path, y_path = _resolve_train_files(project)

    result = data_analysis.run_filtering(x_path, y_path)
    return {
        "n_features": result["n_features"],
        "n_samples": result["n_samples"],
        "n_classes": result["n_classes"],
        "class_labels": result["class_labels"],
        "class_counts": result["class_counts"],
    }


@router.get("/{project_id}/feature-stats")
async def get_feature_stats(
    project_id: str,
    method: str = "wilcoxon",
    prevalence_pct: float = 10.0,
    max_pvalue: float = 0.05,
    min_feature_value: float = 0.0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get per-feature statistics computed by the Rust filtering engine (viewer access).

    Returns all features with their stats (mean, std, prevalence, significance, class).
    """
    if method not in ("wilcoxon", "studentt", "bayesian_fisher"):
        raise HTTPException(400, f"Invalid method: {method}")

    project, _ = await get_project_with_access(project_id, user, db, require_role="viewer")
    x_path, y_path = _resolve_train_files(project)

    result = data_analysis.run_filtering(
        x_path, y_path,
        method=method,
        prevalence_pct=prevalence_pct,
        max_pvalue=max_pvalue,
        min_feature_value=min_feature_value,
    )
    return {
        "features": result["features"],
        "selected_count": result["selected_count"],
        "method": result["method"],
        "n_features": result["n_features"],
    }


@router.get("/{project_id}/distributions")
async def get_distributions(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get pre-binned histogram data for prevalence and SD distributions (viewer access)."""
    project, _ = await get_project_with_access(project_id, user, db, require_role="viewer")
    x_path, y_path = _resolve_train_files(project)

    result = data_analysis.run_filtering(x_path, y_path)
    distributions = data_analysis.compute_distributions(result["features"])
    distributions["class_distribution"] = result["class_counts"]
    return distributions


@router.get("/{project_id}/feature-abundance")
async def get_feature_abundance(
    project_id: str,
    features: str = "",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get boxplot summary stats per class for selected features (viewer access).

    Pass feature names as comma-separated string, max 100.
    """
    if not features:
        raise HTTPException(400, "No features specified")

    feature_list = [f.strip() for f in features.split(",") if f.strip()][:100]
    if not feature_list:
        raise HTTPException(400, "No valid features specified")

    project, _ = await get_project_with_access(project_id, user, db, require_role="viewer")
    x_path, y_path = _resolve_train_files(project)

    abundance = data_analysis.compute_feature_abundance(
        x_path, y_path, feature_list
    )
    return {"features": abundance}


@router.get("/{project_id}/barcode-data")
async def get_barcode_data(
    project_id: str,
    features: str = "",
    max_samples: int = 500,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get raw feature values per sample for barcode heatmap (viewer access).

    Returns a matrix of shape (n_features, n_samples) with samples ordered by class.
    Pass feature names as comma-separated string, max 100.
    """
    if not features:
        raise HTTPException(400, "No features specified")

    feature_list = [f.strip() for f in features.split(",") if f.strip()][:100]
    if not feature_list:
        raise HTTPException(400, "No valid features specified")

    project, _ = await get_project_with_access(project_id, user, db, require_role="viewer")
    x_path, y_path = _resolve_train_files(project)

    barcode = data_analysis.compute_barcode_data(
        x_path, y_path, feature_list, max_samples=max_samples
    )
    return barcode
