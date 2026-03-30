"""Sample/demo dataset endpoints — lets any user load bundled demo data."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.database import get_db
from ..core.deps import get_current_user
from ..models.db_models import User, Project, Dataset, DatasetFile, ProjectDataset
from ..models.schemas import ProjectInfo, DatasetRef, DatasetFileRef
from ..services import storage
from .datasets import _infer_role

router = APIRouter(prefix="/samples", tags=["samples"])

# Datasets bundled with the app
SAMPLE_DATASETS = {
    "qin2014_cirrhosis": {
        "name": "Qin2014 Liver Cirrhosis",
        "description": "Qin N et al., Nature 2014 — 1,980 MSP features, 180 train + 30 test samples",
        "files": [
            {"filename": "Xtrain.tsv", "features_in_rows": True},
            {"filename": "Ytrain.tsv", "features_in_rows": False},
            {"filename": "Xtest.tsv", "features_in_rows": True},
            {"filename": "Ytest.tsv", "features_in_rows": False},
        ],
    },
    "derosa2025_ici": {
        "name": "Derosa2025 ICI Response",
        "description": "Derosa L et al., 2025 — 2,834 MSP features, 229 discovery + 188 validation samples, OS12 endpoint",
        "files": [
            {"filename": "Xtrain.tsv", "features_in_rows": True},
            {"filename": "Ytrain.tsv", "features_in_rows": False},
            {"filename": "Xtest.tsv", "features_in_rows": True},
            {"filename": "Ytest.tsv", "features_in_rows": False},
        ],
    },
    "wetlab_protocol": {
        "name": "Wetlab Protocol (Lysis Effect)",
        "description": "Paired study — 459 subjects, 2 extraction protocols (with/without mechanical lysis), 1,981 MSP features, 734 train + 184 test. Includes metadata (age, sex, BMI, Gram+/- counts, gene_count).",
        "files": [
            {"filename": "Xtrain.tsv", "features_in_rows": True},
            {"filename": "Ytrain.tsv", "features_in_rows": False},
            {"filename": "Xtest.tsv", "features_in_rows": True},
            {"filename": "Ytest.tsv", "features_in_rows": False},
            {"filename": "metadata.tsv", "features_in_rows": False},
        ],
    },
}


@router.get("/")
async def list_samples():
    """List available sample datasets."""
    result = []
    for key, info in SAMPLE_DATASETS.items():
        sample_dir = settings.samples_dir / key
        available = sample_dir.exists()
        result.append({
            "id": key,
            "name": info["name"],
            "description": info["description"],
            "available": available,
            "files": [f["filename"] for f in info["files"]],
        })
    return result


@router.post("/{sample_id}/load", response_model=ProjectInfo)
async def load_sample(
    sample_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a project and load a sample dataset into it for the current user.

    If the user already has a project loaded from this sample, return the
    existing project instead of creating a duplicate.
    """
    if sample_id not in SAMPLE_DATASETS:
        raise HTTPException(status_code=404, detail="Sample dataset not found")

    sample = SAMPLE_DATASETS[sample_id]
    sample_dir = settings.samples_dir / sample_id

    if not sample_dir.exists():
        raise HTTPException(status_code=404, detail="Sample data files not found on disk")

    # Check if user already has a project from this sample
    from .projects import _project_query_options, _build_project_info
    existing = await db.execute(
        select(Project)
        .where(Project.user_id == user.id, Project.name == sample["name"])
        .options(*_project_query_options())
    )
    existing_project = existing.scalars().first()
    if existing_project:
        return _build_project_info(existing_project)

    # Create project
    project = Project(name=sample["name"], user_id=user.id)
    db.add(project)
    await db.flush()
    storage.ensure_project_dirs(project.id)

    # Create ONE composite dataset group in user's library
    dataset = Dataset(
        name=sample["name"],
        description=sample["description"],
        user_id=user.id,
    )
    db.add(dataset)
    await db.flush()

    # Add each file to the dataset group
    file_refs = []
    for file_info in sample["files"]:
        filepath = sample_dir / file_info["filename"]
        if not filepath.exists():
            continue

        content = filepath.read_bytes()
        role = _infer_role(file_info["filename"])

        ds_file = DatasetFile(
            dataset_id=dataset.id,
            filename=file_info["filename"],
            role=role,
            disk_path="",
        )
        db.add(ds_file)
        await db.flush()

        disk_path = storage.save_user_dataset_file(user.id, ds_file.id, file_info["filename"], content)
        ds_file.disk_path = disk_path

        file_refs.append(DatasetFileRef(id=ds_file.id, filename=ds_file.filename, role=ds_file.role))

    # Single assignment to project
    link = ProjectDataset(project_id=project.id, dataset_id=dataset.id)
    db.add(link)
    await db.flush()

    return ProjectInfo(
        project_id=project.id,
        name=project.name,
        created_at=project.created_at.isoformat(),
        datasets=[DatasetRef(id=dataset.id, name=dataset.name, files=file_refs)],
        jobs=[],
    )
