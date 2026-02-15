"""Dataset library endpoints — composite dataset CRUD and project assignment."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Body
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.deps import get_current_user
from ..models.db_models import User, Dataset, DatasetFile, ProjectDataset, Project
from ..models.schemas import DatasetResponse, DatasetFileRef
from ..services import storage

# Pre-defined tag suggestions
SUGGESTED_TAGS = [
    "benchmark", "clinical", "metagenomic", "16S", "shotgun",
    "WGS", "metabolomic", "transcriptomic", "proteomic",
    "public", "private", "test", "production",
]

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _infer_role(filename: str) -> Optional[str]:
    """Infer dataset role from filename convention."""
    name = filename.lower()
    if name.startswith("xtrain") or name == "x.tsv" or name == "x.csv":
        return "xtrain"
    if name.startswith("ytrain") or name == "y.tsv" or name == "y.csv":
        return "ytrain"
    if name.startswith("xtest"):
        return "xtest"
    if name.startswith("ytest"):
        return "ytest"
    return None


def _build_dataset_response(ds: Dataset) -> DatasetResponse:
    """Build a DatasetResponse from a Dataset with loaded files and project_links."""
    files = [
        DatasetFileRef(id=f.id, filename=f.filename, role=f.role)
        for f in ds.files
    ]
    return DatasetResponse(
        id=ds.id,
        name=ds.name,
        description=ds.description,
        tags=ds.tags or [],
        files=files,
        created_at=ds.created_at.isoformat(),
        project_count=len(ds.project_links),
    )


# ---------------------------------------------------------------------------
# Dataset group CRUD
# ---------------------------------------------------------------------------

@router.post("/", response_model=DatasetResponse)
async def create_dataset(
    name: str,
    description: str = "",
    tags: str = "",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new (empty) dataset group."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    dataset = Dataset(name=name, description=description, user_id=user.id, tags=tag_list)
    db.add(dataset)
    await db.flush()

    return DatasetResponse(
        id=dataset.id,
        name=dataset.name,
        description=dataset.description,
        tags=tag_list,
        files=[],
        created_at=dataset.created_at.isoformat(),
        project_count=0,
    )


@router.get("/tags/suggestions")
async def get_tag_suggestions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get suggested tags (predefined + user's existing tags)."""
    result = await db.execute(
        select(Dataset.tags).where(Dataset.user_id == user.id)
    )
    user_tags = set()
    for row in result.scalars().all():
        if row:
            user_tags.update(row)
    all_tags = sorted(set(SUGGESTED_TAGS) | user_tags)
    return {"suggestions": all_tags}


@router.get("/", response_model=list[DatasetResponse])
async def list_datasets(
    tag: Optional[str] = Query(None, description="Filter by tag"),
    search: Optional[str] = Query(None, description="Search by name"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all datasets owned by the current user, optionally filtered by tag or name."""
    query = (
        select(Dataset)
        .where(Dataset.user_id == user.id)
        .options(selectinload(Dataset.files), selectinload(Dataset.project_links))
        .order_by(Dataset.created_at.desc())
    )
    result = await db.execute(query)
    datasets = result.scalars().all()

    # Filter in Python (JSON column filtering varies by DB engine)
    if tag:
        datasets = [d for d in datasets if d.tags and tag in d.tags]
    if search:
        term = search.lower()
        datasets = [d for d in datasets if term in d.name.lower() or term in (d.description or "").lower()]

    return [_build_dataset_response(d) for d in datasets]


@router.get("/{dataset_id}", response_model=DatasetResponse)
async def get_dataset(
    dataset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get details of a specific dataset."""
    result = await db.execute(
        select(Dataset)
        .where(Dataset.id == dataset_id, Dataset.user_id == user.id)
        .options(selectinload(Dataset.files), selectinload(Dataset.project_links))
    )
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return _build_dataset_response(dataset)


@router.delete("/{dataset_id}")
async def delete_dataset(
    dataset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a dataset group and all its files."""
    result = await db.execute(
        select(Dataset)
        .where(Dataset.id == dataset_id, Dataset.user_id == user.id)
        .options(selectinload(Dataset.files))
    )
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Delete physical files
    for f in dataset.files:
        storage.delete_user_dataset_file(f.disk_path)

    await db.delete(dataset)
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Tag management
# ---------------------------------------------------------------------------

@router.patch("/{dataset_id}/tags", response_model=DatasetResponse)
async def update_tags(
    dataset_id: str,
    tags: list[str] = Body(..., embed=True),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Replace all tags on a dataset."""
    result = await db.execute(
        select(Dataset)
        .where(Dataset.id == dataset_id, Dataset.user_id == user.id)
        .options(selectinload(Dataset.files), selectinload(Dataset.project_links))
    )
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Clean and deduplicate tags
    clean_tags = list(dict.fromkeys(t.strip() for t in tags if t.strip()))
    dataset.tags = clean_tags
    await db.flush()
    return _build_dataset_response(dataset)


# ---------------------------------------------------------------------------
# File management within a dataset
# ---------------------------------------------------------------------------

@router.post("/{dataset_id}/files", response_model=DatasetFileRef)
async def upload_file(
    dataset_id: str,
    file: UploadFile = File(...),
    role: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file into an existing dataset group."""
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id, Dataset.user_id == user.id)
    )
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    content = await file.read()

    # Auto-infer role from filename if not specified
    if role is None:
        role = _infer_role(file.filename)

    ds_file = DatasetFile(
        dataset_id=dataset.id,
        filename=file.filename,
        role=role,
        disk_path="",
    )
    db.add(ds_file)
    await db.flush()

    disk_path = storage.save_user_dataset_file(user.id, ds_file.id, file.filename, content)
    ds_file.disk_path = disk_path

    return DatasetFileRef(id=ds_file.id, filename=ds_file.filename, role=ds_file.role)


@router.delete("/{dataset_id}/files/{file_id}")
async def delete_file(
    dataset_id: str,
    file_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single file from a dataset group."""
    result = await db.execute(
        select(DatasetFile)
        .join(Dataset)
        .where(
            DatasetFile.id == file_id,
            DatasetFile.dataset_id == dataset_id,
            Dataset.user_id == user.id,
        )
    )
    ds_file = result.scalar_one_or_none()
    if not ds_file:
        raise HTTPException(status_code=404, detail="File not found")

    storage.delete_user_dataset_file(ds_file.disk_path)
    await db.delete(ds_file)
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Project assignment
# ---------------------------------------------------------------------------

@router.post("/{dataset_id}/assign/{project_id}")
async def assign_dataset(
    dataset_id: str,
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Assign a dataset group to a project."""
    # Verify dataset ownership
    ds_result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id, Dataset.user_id == user.id)
    )
    if not ds_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Verify project ownership
    proj_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user.id)
    )
    if not proj_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if already assigned
    existing = await db.execute(
        select(ProjectDataset).where(
            ProjectDataset.project_id == project_id,
            ProjectDataset.dataset_id == dataset_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Dataset already assigned to this project")

    link = ProjectDataset(project_id=project_id, dataset_id=dataset_id)
    db.add(link)
    await db.flush()
    return {"status": "assigned"}


@router.delete("/{dataset_id}/assign/{project_id}")
async def unassign_dataset(
    dataset_id: str,
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a dataset assignment from a project."""
    result = await db.execute(
        select(ProjectDataset)
        .join(Dataset)
        .where(
            ProjectDataset.project_id == project_id,
            ProjectDataset.dataset_id == dataset_id,
            Dataset.user_id == user.id,
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Assignment not found")

    await db.delete(link)
    return {"status": "unassigned"}
