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
from ..services import storage, quota
from ..models.api_schemas import SampleInfo
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

# Pasolli et al. 2016 (PLoS Comput Biol) benchmark: six binary disease-prediction
# tasks on MetaPhlAn2 species profiles (relative abundance), stratified 80/20 split.
_PASOLLI_FILES = [
    {"filename": "Xtrain.tsv", "features_in_rows": True},
    {"filename": "Ytrain.tsv", "features_in_rows": False},
    {"filename": "Xtest.tsv", "features_in_rows": True},
    {"filename": "Ytest.tsv", "features_in_rows": False},
    {"filename": "metadata.tsv", "features_in_rows": False},
]
for _key, _name, _desc in (
    ("pasolli2016_cirrhosis", "Pasolli2016 Liver Cirrhosis",
     "Pasolli et al. 2016 benchmark — Qin N et al. 2014 cohort, cirrhosis vs healthy, "
     "542 MetaPhlAn2 species, 185 train + 47 test samples"),
    ("pasolli2016_colorectal", "Pasolli2016 Colorectal Cancer",
     "Pasolli et al. 2016 benchmark — Zeller et al. 2014 cohort, CRC vs controls (incl. small adenomas), "
     "503 MetaPhlAn2 species, 96 train + 25 test samples"),
    ("pasolli2016_ibd", "Pasolli2016 IBD",
     "Pasolli et al. 2016 benchmark — MetaHIT cohort, IBD (Crohn's + ulcerative colitis) vs controls, "
     "443 MetaPhlAn2 species, 88 train + 22 test samples"),
    ("pasolli2016_obesity", "Pasolli2016 Obesity",
     "Pasolli et al. 2016 benchmark — Le Chatelier et al. 2013 cohort, obese vs lean, "
     "465 MetaPhlAn2 species, 202 train + 51 test samples"),
    ("pasolli2016_t2d", "Pasolli2016 Type 2 Diabetes (China)",
     "Pasolli et al. 2016 benchmark — Qin J et al. 2012 cohort, T2D vs controls, "
     "572 MetaPhlAn2 species, 275 train + 69 test samples"),
    ("pasolli2016_wt2d", "Pasolli2016 Type 2 Diabetes (European women)",
     "Pasolli et al. 2016 benchmark — Karlsson et al. 2013 cohort, T2D vs normal glucose tolerance, "
     "381 MetaPhlAn2 species, 76 train + 20 test samples"),
):
    SAMPLE_DATASETS[_key] = {"name": _name, "description": _desc, "files": _PASOLLI_FILES}


@router.get("/", response_model=list[SampleInfo])
async def list_samples():
    """List available sample datasets.

    Deliberately public: it is the static catalogue of the demo datasets shipped
    with the application (names, citations, file names) and contains nothing
    about users or this installation. Loading a sample requires an account.
    """
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

    # The sample files are copied into the user's library and count toward their quota.
    needed = sum(
        (sample_dir / f["filename"]).stat().st_size
        for f in sample["files"] if (sample_dir / f["filename"]).exists()
    )
    await quota.check_quota(db, user.id, needed)

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
