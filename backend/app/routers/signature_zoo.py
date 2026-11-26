"""Signature Zoo: curated database of published biomarker signatures."""

import asyncio
import json
import os
import uuid
import fcntl
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.database import get_db
from ..core.deps import get_current_user, get_admin_user, get_project_with_access
from ..models.db_models import User, Job
from ..services import storage
from typing import List
from ..models.schemas import (
    SignatureComparison, SignatureDeleted,
)

ZOO_PATH = Path(settings.data_dir) / "signature_zoo.json"

router = APIRouter(prefix="/signature-zoo", tags=["signature-zoo"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class Publication(BaseModel):
    author: str = ""
    year: Optional[int] = None
    journal: str = ""
    doi: str = ""


class CohortInfo(BaseModel):
    n_samples: Optional[int] = None
    n_cases: Optional[int] = None
    n_controls: Optional[int] = None
    population: str = ""
    country: str = ""


class FeatureEntry(BaseModel):
    name: str
    coefficient: float = 0.0
    direction: str = "enriched"  # "enriched" | "depleted"


class Performance(BaseModel):
    auc: Optional[float] = None
    accuracy: Optional[float] = None
    sensitivity: Optional[float] = None
    specificity: Optional[float] = None


class SignatureBase(BaseModel):
    name: str
    disease: str = ""
    phenotype: str = ""
    method: str = ""
    publication: Publication = Publication()
    cohort_info: CohortInfo = CohortInfo()
    features: list[FeatureEntry] = []
    performance: Performance = Performance()
    tags: list[str] = []


class SignatureCreate(SignatureBase):
    pass


class SignatureUpdate(SignatureBase):
    pass


class SignatureResponse(SignatureBase):
    id: str
    created_at: str = ""
    created_by: str = "system"


class ImportFromJobRequest(BaseModel):
    job_id: str
    project_id: str
    name: str
    disease: str = ""
    phenotype: str = ""
    method: str = ""
    publication: Publication = Publication()
    cohort_info: CohortInfo = CohortInfo()
    tags: list[str] = []


# ---------------------------------------------------------------------------
# File I/O helpers (with locking)
# ---------------------------------------------------------------------------

_LOCK_PATH = ZOO_PATH.with_suffix(".lock")


@contextmanager
def _zoo_lock():
    """Exclusive lock on a sidecar file, held for a whole read-modify-write cycle."""
    ZOO_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOCK_PATH, "w") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _load_signatures() -> list[dict]:
    """Read all signatures from the JSON file.

    A missing file is an empty zoo. A corrupt file raises instead of returning
    ``[]``: treating it as empty would let the next save wipe every entry.
    """
    if not ZOO_PATH.exists():
        return []
    with open(ZOO_PATH, "r") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("signature_zoo.json is not a list")
    return data


def _save_signatures(sigs: list[dict]) -> None:
    """Replace the JSON file atomically (write a temp file, then rename)."""
    ZOO_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = ZOO_PATH.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(sigs, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ZOO_PATH)


def _read_zoo() -> list[dict]:
    try:
        return _load_signatures()
    except (ValueError, OSError):
        raise HTTPException(status_code=500, detail="The signature collection could not be read")


def _mutate_zoo(fn):
    """Run ``fn(sigs)`` under the lock and persist; returns fn's result."""
    with _zoo_lock():
        sigs = _read_zoo()
        result = fn(sigs)
        _save_signatures(sigs)
        return result


def _public(sig: dict) -> dict:
    """Signature as shown to anonymous visitors: no contributor email."""
    return {**sig, "created_by": "contributor" if sig.get("created_by") not in (None, "", "system") else "system"}


def _owner_id(sig: dict) -> Optional[str]:
    return sig.get("created_by_id")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[SignatureResponse])
async def list_signatures(
    disease: Optional[str] = Query(None, description="Filter by disease/phenotype"),
    method: Optional[str] = Query(None, description="Filter by method"),
    search: Optional[str] = Query(None, description="Text search in name and features"),
):
    """List all signatures with optional filters. Public, no auth required."""
    sigs = await asyncio.to_thread(_read_zoo)

    if disease:
        dl = disease.lower()
        sigs = [s for s in sigs if dl in s.get("disease", "").lower() or dl in s.get("phenotype", "").lower()]

    if method:
        ml = method.lower()
        sigs = [s for s in sigs if ml in s.get("method", "").lower()]

    if search:
        sl = search.lower()
        filtered = []
        for s in sigs:
            if sl in s.get("name", "").lower():
                filtered.append(s)
                continue
            # Search in feature names
            if any(sl in f.get("name", "").lower() for f in s.get("features", [])):
                filtered.append(s)
                continue
            # Search in tags
            if any(sl in t.lower() for t in s.get("tags", [])):
                filtered.append(s)
        sigs = filtered

    return [_public(s) for s in sigs]


@router.get("/compare", response_model=SignatureComparison, response_model_exclude_unset=True)
async def compare_signatures(
    ids: str = Query(..., description="Comma-separated signature IDs"),
):
    """Compare multiple signatures: feature overlap and performance comparison."""
    id_list = [x.strip() for x in ids.split(",") if x.strip()]
    if len(id_list) < 2:
        raise HTTPException(status_code=400, detail="Provide at least 2 signature IDs")

    sigs = await asyncio.to_thread(_read_zoo)
    sig_map = {s["id"]: s for s in sigs}

    selected = []
    for sid in id_list:
        if sid not in sig_map:
            raise HTTPException(status_code=404, detail=f"Signature {sid} not found")
        selected.append(sig_map[sid])

    # Build feature overlap matrix
    # For each feature name, which signatures contain it
    feature_presence = {}  # feature_name -> list of sig ids
    for sig in selected:
        for feat in sig.get("features", []):
            fname = feat["name"]
            if fname not in feature_presence:
                feature_presence[fname] = []
            feature_presence[fname].append(sig["id"])

    # Find common features (in all selected) and unique features
    all_features = set(feature_presence.keys())
    common_features = [f for f, sids in feature_presence.items() if len(sids) == len(selected)]
    unique_features = {
        sig["id"]: [
            f["name"] for f in sig.get("features", [])
            if len(feature_presence.get(f["name"], [])) == 1
        ]
        for sig in selected
    }

    # Performance comparison
    performance_comparison = []
    for sig in selected:
        perf = sig.get("performance", {})
        performance_comparison.append({
            "id": sig["id"],
            "name": sig["name"],
            "disease": sig.get("disease", ""),
            "method": sig.get("method", ""),
            "auc": perf.get("auc"),
            "accuracy": perf.get("accuracy"),
            "sensitivity": perf.get("sensitivity"),
            "specificity": perf.get("specificity"),
            "feature_count": len(sig.get("features", [])),
        })

    # Overlap matrix (pairwise Jaccard)
    overlap_matrix = []
    for i, s1 in enumerate(selected):
        row = []
        features1 = set(f["name"] for f in s1.get("features", []))
        for j, s2 in enumerate(selected):
            features2 = set(f["name"] for f in s2.get("features", []))
            intersection = features1 & features2
            union = features1 | features2
            jaccard = len(intersection) / len(union) if union else 0
            row.append({
                "shared": len(intersection),
                "jaccard": round(jaccard, 4),
            })
        overlap_matrix.append(row)

    return {
        "signatures": [{"id": s["id"], "name": s["name"]} for s in selected],
        "feature_presence": feature_presence,
        "common_features": common_features,
        "unique_features": unique_features,
        "performance_comparison": performance_comparison,
        "overlap_matrix": overlap_matrix,
    }


@router.get("/{signature_id}", response_model=SignatureResponse)
async def get_signature(signature_id: str):
    """Get a single signature by ID. Public, no auth required."""
    sigs = await asyncio.to_thread(_read_zoo)
    for s in sigs:
        if s["id"] == signature_id:
            return _public(s)
    raise HTTPException(status_code=404, detail="Signature not found")


@router.post("/", response_model=SignatureResponse)
async def create_signature(
    body: SignatureCreate,
    user: User = Depends(get_current_user),
):
    """Add a new signature (auth required)."""
    new_sig = body.model_dump()
    new_sig["id"] = uuid.uuid4().hex[:12]
    new_sig["created_at"] = datetime.now(timezone.utc).isoformat()
    new_sig["created_by"] = user.email
    new_sig["created_by_id"] = user.id

    await asyncio.to_thread(_mutate_zoo, lambda sigs: sigs.append(new_sig))
    return new_sig


@router.put("/{signature_id}", response_model=SignatureResponse)
async def update_signature(
    signature_id: str,
    body: SignatureUpdate,
    user: User = Depends(get_current_user),
):
    """Update a signature. Only its creator or an administrator may do so."""
    updated = body.model_dump()

    def _apply(sigs: list[dict]):
        for i, s in enumerate(sigs):
            if s["id"] == signature_id:
                is_creator = _owner_id(s) == user.id or (
                    _owner_id(s) is None and s.get("created_by") == user.email
                )
                if not (user.is_admin or is_creator):
                    raise HTTPException(status_code=403, detail="Only the creator or an administrator can edit this signature")
                updated["id"] = signature_id
                updated["created_at"] = s.get("created_at", "")
                updated["created_by"] = s.get("created_by", user.email)
                if s.get("created_by_id"):
                    updated["created_by_id"] = s["created_by_id"]
                sigs[i] = updated
                return updated
        raise HTTPException(status_code=404, detail="Signature not found")

    return await asyncio.to_thread(_mutate_zoo, _apply)


@router.delete("/{signature_id}", response_model=SignatureDeleted, response_model_exclude_unset=True)
async def delete_signature(
    signature_id: str,
    admin: User = Depends(get_admin_user),
):
    """Delete a signature (admin only)."""
    def _apply(sigs: list[dict]):
        kept = [s for s in sigs if s["id"] != signature_id]
        if len(kept) == len(sigs):
            raise HTTPException(status_code=404, detail="Signature not found")
        sigs[:] = kept

    await asyncio.to_thread(_mutate_zoo, _apply)
    return {"status": "deleted", "id": signature_id}


@router.post("/import-from-job", response_model=SignatureResponse)
async def import_from_job(
    body: ImportFromJobRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a signature entry from a completed job's best model.

    The caller must have access to the job's project (viewer or better).
    """
    if not storage.is_safe_id(body.project_id) or not storage.is_safe_id(body.job_id):
        raise HTTPException(status_code=404, detail="Job results not found")
    await get_project_with_access(body.project_id, user, db, require_role="viewer")
    job = (await db.execute(
        select(Job).where(Job.id == body.job_id, Job.project_id == body.project_id)
    )).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job results not found")

    results = await asyncio.to_thread(storage.get_job_result, body.project_id, body.job_id)
    if not results:
        raise HTTPException(
            status_code=404,
            detail="Job results not found. Ensure the job has completed successfully.",
        )

    best = results.get("best_individual") or {}

    # Feature names: sklearn results carry them directly; gpredomics results
    # give {feature index: coefficient} to be resolved against feature_names.
    named_features = dict(best.get("named_features") or {})
    if not named_features:
        feature_names = results.get("feature_names") or []
        for idx_str, coef in (best.get("features") or {}).items():
            try:
                idx = int(idx_str)
                name = feature_names[idx] if 0 <= idx < len(feature_names) else f"feature_{idx}"
                named_features[name] = float(coef)
            except (TypeError, ValueError):
                continue
    if not named_features:
        raise HTTPException(status_code=422, detail="This job's best model has no features to import")

    features = []
    for fname, coef in named_features.items():
        features.append({
            "name": fname,
            "coefficient": coef,
            "direction": "enriched" if coef > 0 else "depleted",
        })

    # Extract performance
    perf = {
        "auc": best.get("auc"),
        "accuracy": best.get("accuracy"),
        "sensitivity": best.get("sensitivity"),
        "specificity": best.get("specificity"),
    }

    # Build signature
    new_sig = {
        "id": uuid.uuid4().hex[:12],
        "name": body.name,
        "disease": body.disease,
        "phenotype": body.phenotype,
        "method": body.method or best.get("language", "Predomics"),
        "publication": body.publication.model_dump(),
        "cohort_info": body.cohort_info.model_dump(),
        "features": features,
        "performance": perf,
        "tags": body.tags,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user.email,
        "created_by_id": user.id,
    }

    await asyncio.to_thread(_mutate_zoo, lambda sigs: sigs.append(new_sig))
    return new_sig
