"""Signature Zoo: curated database of published biomarker signatures."""

import json
import uuid
import fcntl
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..core.config import settings
from ..core.deps import get_current_user, get_admin_user
from ..models.db_models import User

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

def _load_signatures() -> list[dict]:
    """Read all signatures from the JSON file."""
    if not ZOO_PATH.exists():
        return []
    try:
        with open(ZOO_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_signatures(sigs: list[dict]) -> None:
    """Write all signatures to the JSON file with file locking."""
    ZOO_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ZOO_PATH, "w") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            json.dump(sigs, f, indent=2, ensure_ascii=False)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


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
    sigs = _load_signatures()

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

    return sigs


@router.get("/compare")
async def compare_signatures(
    ids: str = Query(..., description="Comma-separated signature IDs"),
):
    """Compare multiple signatures: feature overlap and performance comparison."""
    id_list = [x.strip() for x in ids.split(",") if x.strip()]
    if len(id_list) < 2:
        raise HTTPException(status_code=400, detail="Provide at least 2 signature IDs")

    sigs = _load_signatures()
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
    sigs = _load_signatures()
    for s in sigs:
        if s["id"] == signature_id:
            return s
    raise HTTPException(status_code=404, detail="Signature not found")


@router.post("/", response_model=SignatureResponse)
async def create_signature(
    body: SignatureCreate,
    user: User = Depends(get_current_user),
):
    """Add a new signature (auth required)."""
    sigs = _load_signatures()

    new_sig = body.model_dump()
    new_sig["id"] = uuid.uuid4().hex[:12]
    new_sig["created_at"] = datetime.now(timezone.utc).isoformat()
    new_sig["created_by"] = user.email

    sigs.append(new_sig)
    _save_signatures(sigs)
    return new_sig


@router.put("/{signature_id}", response_model=SignatureResponse)
async def update_signature(
    signature_id: str,
    body: SignatureUpdate,
    user: User = Depends(get_current_user),
):
    """Update an existing signature (auth required)."""
    sigs = _load_signatures()

    for i, s in enumerate(sigs):
        if s["id"] == signature_id:
            updated = body.model_dump()
            updated["id"] = signature_id
            updated["created_at"] = s.get("created_at", "")
            updated["created_by"] = s.get("created_by", user.email)
            sigs[i] = updated
            _save_signatures(sigs)
            return updated

    raise HTTPException(status_code=404, detail="Signature not found")


@router.delete("/{signature_id}")
async def delete_signature(
    signature_id: str,
    admin: User = Depends(get_admin_user),
):
    """Delete a signature (admin only)."""
    sigs = _load_signatures()
    new_sigs = [s for s in sigs if s["id"] != signature_id]

    if len(new_sigs) == len(sigs):
        raise HTTPException(status_code=404, detail="Signature not found")

    _save_signatures(new_sigs)
    return {"status": "deleted", "id": signature_id}


@router.post("/import-from-job", response_model=SignatureResponse)
async def import_from_job(
    body: ImportFromJobRequest,
    user: User = Depends(get_current_user),
):
    """Create a signature entry from a completed job's best model."""
    # Load job results
    results_path = (
        Path(settings.data_dir) / "projects" / body.project_id
        / "jobs" / body.job_id / "results.json"
    )
    if not results_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Job results not found. Ensure the job has completed successfully.",
        )

    try:
        with open(results_path) as f:
            results = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to read job results: {e}")

    best = results.get("best_individual", {})

    # Extract features
    features = []
    named_features = best.get("named_features", {})
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
    }

    sigs = _load_signatures()
    sigs.append(new_sig)
    _save_signatures(sigs)

    return new_sig
