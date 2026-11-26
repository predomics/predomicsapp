"""Project management endpoints with database and auth."""

import io
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.deps import get_current_user, get_project_access, get_project_with_access
from ..core.uploads import read_upload, check_role
from ..models.db_models import User, Project, Dataset, DatasetFile, ProjectDataset
from ..services import audit
from ..models.schemas import ProjectInfo, ProjectUpdate, DatasetInfo, DatasetRef, DatasetFileRef
from ..services import storage, quota
from ..models.api_schemas import StatusOut
from .datasets import _infer_role

router = APIRouter(prefix="/projects", tags=["projects"])


def _build_project_info(project: Project) -> ProjectInfo:
    """Build ProjectInfo from a Project with loaded relationships."""
    datasets = []
    for link in project.dataset_links:
        ds = link.dataset
        files = [
            DatasetFileRef(id=f.id, filename=f.filename, role=f.role)
            for f in ds.files
        ]
        datasets.append(DatasetRef(id=ds.id, name=ds.name, files=files))

    job_count = len(project.jobs)
    share_count = len(project.shares) if project.shares else 0

    latest_job_status = None
    if project.jobs:
        sorted_jobs = sorted(project.jobs, key=lambda j: j.created_at, reverse=True)
        latest_job_status = sorted_jobs[0].status

    return ProjectInfo(
        project_id=project.id,
        name=project.name,
        description=project.description,
        class_names=project.class_names,
        archived=project.archived,
        created_at=project.created_at.isoformat(),
        updated_at=project.updated_at.isoformat() if project.updated_at else None,
        datasets=datasets,
        jobs=[j.id for j in project.jobs],
        job_count=job_count,
        share_count=share_count,
        latest_job_status=latest_job_status,
    )


def _project_query_options():
    """Common selectinload options for project queries."""
    return [
        selectinload(Project.dataset_links)
            .selectinload(ProjectDataset.dataset)
            .selectinload(Dataset.files),
        selectinload(Project.jobs),
        selectinload(Project.shares),
    ]


@router.post("/", response_model=ProjectInfo)
async def create_project(
    name: str,
    description: str = "",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new project."""
    project = Project(name=name, description=description, user_id=user.id)
    db.add(project)
    await db.flush()

    # Create filesystem directories
    storage.ensure_project_dirs(project.id)
    await audit.log_action(db, user, audit.ACTION_PROJECT_CREATE, "project", project.id)

    return ProjectInfo(
        project_id=project.id,
        name=project.name,
        description=project.description,
        class_names=project.class_names,
        created_at=project.created_at.isoformat(),
        datasets=[],
        jobs=[],
    )


@router.get("/", response_model=list[ProjectInfo])
async def list_projects(
    include_archived: bool = Query(False, description="Include archived projects"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List projects owned by the current user."""
    result = await db.execute(
        select(Project)
        .where(Project.user_id == user.id)
        .options(*_project_query_options())
        .order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()
    if not include_archived:
        projects = [p for p in projects if not p.archived]
    return [_build_project_info(p) for p in projects]


@router.get("/{project_id}", response_model=ProjectInfo)
async def get_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get project details (owner or shared user)."""
    project, _ = await get_project_with_access(project_id, user, db, require_role="viewer")
    return _build_project_info(project)


@router.patch("/{project_id}", response_model=ProjectInfo)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update project name, description, and/or class names (owner only)."""
    project, _ = await get_project_with_access(project_id, user, db, require_role="owner")
    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if body.class_names is not None:
        project.class_names = body.class_names
    project.updated_at = datetime.now(timezone.utc)
    return _build_project_info(project)


@router.delete("/{project_id}", response_model=StatusOut)
async def delete_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a project (owner only). Datasets stay in user library."""
    project, _ = await get_project_with_access(project_id, user, db, require_role="owner")
    active = [j for j in project.jobs if str(getattr(j.status, "value", j.status)) in ("running", "pending")]
    if active:
        raise HTTPException(
            status_code=409,
            detail=f"{len(active)} job(s) are still running or queued. Cancel them or wait before deleting the project.",
        )
    await audit.log_action(db, user, audit.ACTION_PROJECT_DELETE, "project", project_id)
    await db.delete(project)
    # Remove the files only once the database change is durable, so a failed
    # commit cannot leave rows pointing at files that no longer exist.
    await db.commit()
    storage.delete_project_files(project_id)
    return {"status": "deleted"}


@router.post("/{project_id}/archive", response_model=ProjectInfo)
async def toggle_archive(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle archived status of a project (owner only)."""
    project, _ = await get_project_with_access(project_id, user, db, require_role="owner")
    project.archived = not project.archived
    return _build_project_info(project)


@router.post("/{project_id}/datasets", response_model=DatasetInfo)
async def upload_dataset(
    project_id: str,
    file: UploadFile = File(...),
    features_in_rows: bool = True,
    role: Optional[str] = Query(None, description="xtrain, ytrain, xtest, ytest or metadata; inferred from the filename when omitted"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a dataset file to a project (backward compat).

    Creates a dataset group in the user's library with one file,
    then assigns it to the project. Owner or editor access required.
    Pass ``role`` to say what the file is; otherwise it is guessed from the name.
    """
    # Only the access decision is needed here, not the project's datasets and jobs.
    project, _ = await get_project_access(project_id, user, db, require_role="editor")
    role = check_role(role)

    content = await read_upload(file)
    await quota.check_quota(db, user.id, len(content))
    filename = storage.safe_filename(file.filename, default="upload.tsv")

    # Create dataset group in user's library
    dataset = Dataset(name=filename, user_id=user.id)
    db.add(dataset)
    await db.flush()

    # Create file within the dataset group
    role = role or _infer_role(filename)
    ds_file = DatasetFile(
        dataset_id=dataset.id,
        filename=filename,
        role=role,
        disk_path="",
    )
    db.add(ds_file)
    await db.flush()

    # Save to user-level storage
    disk_path = storage.save_user_dataset_file(user.id, ds_file.id, filename, content)
    ds_file.disk_path = disk_path

    # Assign dataset group to project
    link = ProjectDataset(project_id=project_id, dataset_id=dataset.id)
    db.add(link)
    await db.flush()

    # Parse to get info
    try:
        sep = "\t" if filename.endswith(".tsv") else ","
        df = pd.read_csv(io.BytesIO(content), sep=sep, index_col=0)
        if features_in_rows:
            n_features, n_samples = df.shape
        else:
            n_samples, n_features = df.shape
    except Exception:
        n_features, n_samples = 0, 0

    return DatasetInfo(
        filename=filename,
        n_features=n_features,
        n_samples=n_samples,
        n_classes=0,
        features_in_rows=features_in_rows,
    )
