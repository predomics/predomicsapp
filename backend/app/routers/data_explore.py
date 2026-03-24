"""Data exploration endpoints — feature statistics and filtering via Rust engine."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import get_current_user, get_project_with_access
from ..models.db_models import User, Project
from ..services import data_analysis
from ..services import msp_annotations
from ..services import coabundance
from ..services import enrichment
from ..services import insights as insights_service
from ..services import storage
from ..core.config import settings

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


@router.get("/{project_id}/pcoa")
async def get_pcoa(
    project_id: str,
    metric: str = "braycurtis",
    features: str = "",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compute PCoA with confidence ellipses and PERMANOVA (viewer access).

    Returns 3D coordinates, sample classes, % variance explained per axis,
    95% confidence ellipses per class, and PERMANOVA test results.
    Supported metrics: braycurtis (default), euclidean, jaccard, cosine.
    Pass feature names as comma-separated string to restrict to FBM features.
    """
    allowed_metrics = ("braycurtis", "euclidean", "jaccard", "cosine")
    if metric not in allowed_metrics:
        raise HTTPException(400, f"Invalid metric: {metric}. Choose from {allowed_metrics}")

    project, _ = await get_project_with_access(project_id, user, db, require_role="viewer")
    x_path, y_path = _resolve_train_files(project)

    feature_names = None
    if features:
        feature_names = [f.strip() for f in features.split(",") if f.strip()]

    pcoa_result = data_analysis.compute_pcoa(
        x_path, y_path, metric=metric, feature_names=feature_names,
    )
    return pcoa_result


@router.get("/{project_id}/ordination")
async def get_ordination(
    project_id: str,
    method: str = "pcoa",
    metric: str = "braycurtis",
    features: str = "",
    perplexity: float = 30.0,
    n_neighbors: int = 15,
    min_dist: float = 0.1,
    n_components: int = 2,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unified ordination endpoint supporting PCoA, t-SNE, and UMAP (viewer access).

    Returns coordinates, sample classes, confidence ellipses, and PERMANOVA.
    For PCoA, also returns variance_explained per axis.
    """
    allowed_methods = ("pcoa", "tsne", "umap")
    if method not in allowed_methods:
        raise HTTPException(400, f"Invalid method: {method}. Choose from {allowed_methods}")

    allowed_metrics = ("braycurtis", "euclidean", "jaccard", "cosine")
    if metric not in allowed_metrics:
        raise HTTPException(400, f"Invalid metric: {metric}. Choose from {allowed_metrics}")

    project, _ = await get_project_with_access(project_id, user, db, require_role="viewer")
    x_path, y_path = _resolve_train_files(project)

    feature_names = None
    if features:
        feature_names = [f.strip() for f in features.split(",") if f.strip()]

    if method == "tsne":
        result = data_analysis.compute_tsne(
            x_path, y_path, metric=metric, feature_names=feature_names,
            perplexity=perplexity, n_components=n_components,
        )
    elif method == "umap":
        result = data_analysis.compute_umap(
            x_path, y_path, metric=metric, feature_names=feature_names,
            n_neighbors=n_neighbors, min_dist=min_dist, n_components=n_components,
        )
    else:
        result = data_analysis.compute_pcoa(
            x_path, y_path, metric=metric, feature_names=feature_names,
        )
        result["method"] = "pcoa"

    return result


@router.get("/{project_id}/coabundance-network")
async def get_coabundance_network(
    project_id: str,
    min_prevalence_pct: float = 30.0,
    correlation_threshold: float = 0.3,
    class_filter: str = "all",
    features: str = "",
    job_id: str = "",
    community_method: str = "louvain",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compute co-abundance ecosystem network from the abundance matrix (viewer access).

    Returns nodes with taxonomy coloring, edges with Spearman correlations,
    community modules, and optional FBM annotation.
    """
    if class_filter not in ("all", "0", "1"):
        raise HTTPException(400, f"Invalid class_filter: {class_filter}. Choose from all, 0, 1")

    if community_method not in ("louvain", "greedy", "label_propagation"):
        raise HTTPException(400, f"Invalid community_method: {community_method}. Choose from louvain, greedy, label_propagation")

    project, _ = await get_project_with_access(project_id, user, db, require_role="viewer")
    x_path, y_path = _resolve_train_files(project)

    feature_names = None
    if features:
        feature_names = [f.strip() for f in features.split(",") if f.strip()]

    job_results = None
    if job_id:
        job_results = storage.get_job_result(project_id, job_id)

    result = coabundance.compute_coabundance_network(
        x_path, y_path,
        min_prevalence_pct=min_prevalence_pct,
        correlation_threshold=correlation_threshold,
        class_filter=class_filter,
        feature_names=feature_names,
        job_results=job_results,
        community_method=community_method,
    )
    return result


@router.get("/{project_id}/aberrant-correlations")
async def get_aberrant_correlations(
    project_id: str,
    min_prevalence_pct: float = 30.0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """QC scatter: control vs patient correlations to validate prevalence thresholds."""
    project, _ = await get_project_with_access(project_id, user, db, require_role="viewer")
    x_path, y_path = _resolve_train_files(project)
    result = data_analysis.compute_aberrant_correlations(
        x_path, y_path, min_prevalence_pct=min_prevalence_pct,
    )
    return result


@router.get("/{project_id}/dual-network")
async def get_dual_network(
    project_id: str,
    min_prevalence_pct: float = 30.0,
    correlation_threshold: float = 0.3,
    community_method: str = "louvain",
    job_id: str = "",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Side-by-side patient vs control co-abundance ecosystems.

    Computes networks for class 0 and class 1 separately and compares edges.
    Returns both networks plus comparison stats (common, specific to each class).
    """
    if community_method not in ("louvain", "greedy", "label_propagation"):
        raise HTTPException(400, f"Invalid community_method: {community_method}")

    project, _ = await get_project_with_access(project_id, user, db, require_role="viewer")
    x_path, y_path = _resolve_train_files(project)

    job_results = None
    if job_id:
        job_results = storage.get_job_result(project_id, job_id)

    net0 = coabundance.compute_coabundance_network(
        x_path, y_path,
        min_prevalence_pct=min_prevalence_pct,
        correlation_threshold=correlation_threshold,
        class_filter="0",
        job_results=job_results,
        community_method=community_method,
    )
    net1 = coabundance.compute_coabundance_network(
        x_path, y_path,
        min_prevalence_pct=min_prevalence_pct,
        correlation_threshold=correlation_threshold,
        class_filter="1",
        job_results=job_results,
        community_method=community_method,
    )

    # Compare edges
    edges0 = {(e["source"], e["target"]) for e in net0["edges"]}
    edges1 = {(e["source"], e["target"]) for e in net1["edges"]}
    # Also check reverse direction
    edges0_both = edges0 | {(t, s) for s, t in edges0}
    edges1_both = edges1 | {(t, s) for s, t in edges1}

    common = edges0 & edges1
    specific_0 = edges0 - edges1
    specific_1 = edges1 - edges0

    # Mark edges in each network
    for e in net0["edges"]:
        key = (e["source"], e["target"])
        e["shared"] = key in edges1_both
    for e in net1["edges"]:
        key = (e["source"], e["target"])
        e["shared"] = key in edges0_both

    # Compute module correspondence (Sankey data)
    # Build species->module mapping for each class
    species_mod0 = {}
    for node in net0["nodes"]:
        species_mod0[node["id"]] = node["module"]
    species_mod1 = {}
    for node in net1["nodes"]:
        species_mod1[node["id"]] = node["module"]

    # Count shared species between each pair of modules
    common_species = set(species_mod0.keys()) & set(species_mod1.keys())
    flow_counts = {}  # (mod0, mod1) -> count
    for sp in common_species:
        m0 = species_mod0[sp]
        m1 = species_mod1[sp]
        flow_counts[(m0, m1)] = flow_counts.get((m0, m1), 0) + 1

    # Build Sankey-ready structure
    sankey_links = []
    for (m0, m1), count in sorted(flow_counts.items()):
        sankey_links.append({"source_module": m0, "target_module": m1, "value": count})

    return {
        "network_0": net0,
        "network_1": net1,
        "comparison": {
            "common_edges": len(common),
            "specific_0": len(specific_0),
            "specific_1": len(specific_1),
            "nodes_0": net0["stats"]["n_nodes"],
            "nodes_1": net1["stats"]["n_nodes"],
            "common_species": len(common_species),
        },
        "sankey_links": sankey_links,
    }


@router.post("/{project_id}/external-networks")
async def upload_external_network(
    project_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload an external network JSON file for overlay visualization."""
    project, _ = await get_project_with_access(project_id, user, db, require_role="editor")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(400, "Network file too large (max 10MB)")

    try:
        net_data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON file")

    # Validate structure
    if "nodes" not in net_data or not isinstance(net_data["nodes"], list):
        raise HTTPException(400, "JSON must contain a 'nodes' array")
    if "edges" not in net_data or not isinstance(net_data["edges"], list):
        raise HTTPException(400, "JSON must contain an 'edges' array")

    # Save to project directory
    import uuid as _uuid
    net_id = str(_uuid.uuid4())[:8]
    net_name = net_data.get("metadata", {}).get("name", file.filename or "external")

    storage.ensure_project_dirs(project_id)
    net_dir = settings.project_dir / project_id / "networks"
    net_dir.mkdir(parents=True, exist_ok=True)
    dest = net_dir / f"{net_id}.json"
    dest.write_bytes(content)

    return {
        "id": net_id,
        "name": net_name,
        "filename": file.filename,
        "n_nodes": len(net_data["nodes"]),
        "n_edges": len(net_data["edges"]),
    }


@router.get("/{project_id}/external-networks")
async def list_external_networks(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List uploaded external networks for a project."""
    project, _ = await get_project_with_access(project_id, user, db, require_role="viewer")

    net_dir = settings.project_dir / project_id / "networks"
    if not net_dir.exists():
        return []

    networks = []
    for f in sorted(net_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            networks.append({
                "id": f.stem,
                "name": data.get("metadata", {}).get("name", f.stem),
                "n_nodes": len(data.get("nodes", [])),
                "n_edges": len(data.get("edges", [])),
            })
        except Exception:
            continue
    return networks


@router.get("/{project_id}/external-networks/{network_id}")
async def get_external_network(
    project_id: str,
    network_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve an uploaded external network."""
    project, _ = await get_project_with_access(project_id, user, db, require_role="viewer")

    net_path = settings.project_dir / project_id / "networks" / f"{network_id}.json"
    if not net_path.exists():
        raise HTTPException(404, "Network not found")

    data = json.loads(net_path.read_text())
    return data


@router.delete("/{project_id}/external-networks/{network_id}")
async def delete_external_network(
    project_id: str,
    network_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an uploaded external network."""
    project, _ = await get_project_with_access(project_id, user, db, require_role="editor")

    net_path = settings.project_dir / project_id / "networks" / f"{network_id}.json"
    if not net_path.exists():
        raise HTTPException(404, "Network not found")

    net_path.unlink()
    return {"deleted": True}


# --- Reference (built-in) networks ---

_REFERENCE_NETWORKS_DIR = Path(settings.data_dir)
_REFERENCE_NETWORK_FILES = {
    "scapis": "scapis_network.json",
}


@router.get("/reference-networks/list")
async def list_reference_networks():
    """List built-in reference networks shipped with the application."""
    result = []
    for net_id, filename in _REFERENCE_NETWORK_FILES.items():
        path = _REFERENCE_NETWORKS_DIR / filename
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
            meta = data.get("metadata", {})
            result.append({
                "id": net_id,
                "name": meta.get("name", net_id),
                "description": meta.get("description", ""),
                "n_nodes": len(data.get("nodes", [])),
                "n_edges": len(data.get("edges", [])),
                "source": "reference",
            })
        except Exception:
            continue
    return result


@router.get("/reference-networks/{network_id}")
async def get_reference_network(network_id: str):
    """Retrieve a built-in reference network."""
    filename = _REFERENCE_NETWORK_FILES.get(network_id)
    if not filename:
        raise HTTPException(404, f"Reference network '{network_id}' not found")

    path = _REFERENCE_NETWORKS_DIR / filename
    if not path.exists():
        raise HTTPException(404, f"Reference network file missing")

    data = json.loads(path.read_text())
    return data


@router.post("/{project_id}/fbm-module-filter")
async def fbm_module_filter(
    project_id: str,
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Filter the FBM population by ecosystem network modules.

    Keeps only models whose species belong to the selected ecological niche(s).
    Body: {
        "job_id": "...",
        "module_ids": [0, 1],
        "min_prevalence_pct": 30.0,      (optional, default 30)
        "correlation_threshold": 0.3,     (optional, default 0.3)
        "community_method": "louvain"     (optional)
    }
    Returns filtered models with module coherence scores.
    """
    job_id = body.get("job_id")
    module_ids = body.get("module_ids", [])
    min_prevalence_pct = body.get("min_prevalence_pct", 30.0)
    correlation_threshold = body.get("correlation_threshold", 0.3)
    community_method = body.get("community_method", "louvain")

    if not job_id:
        raise HTTPException(400, "job_id is required")
    if not module_ids or not isinstance(module_ids, list):
        raise HTTPException(400, "module_ids must be a non-empty list of module IDs")
    if community_method not in ("louvain", "greedy", "label_propagation"):
        raise HTTPException(400, f"Invalid community_method: {community_method}")

    project, _ = await get_project_with_access(project_id, user, db, require_role="viewer")
    x_path, y_path = _resolve_train_files(project)

    # Load job results to get population
    job_results = storage.get_job_result(project_id, job_id)
    if not job_results:
        raise HTTPException(404, "Job results not found")

    population = job_results.get("population", [])
    if not population:
        raise HTTPException(404, "No population data in job results")

    # Compute (or retrieve cached) the co-abundance network to get module assignments
    network = coabundance.compute_coabundance_network(
        x_path, y_path,
        min_prevalence_pct=min_prevalence_pct,
        correlation_threshold=correlation_threshold,
        community_method=community_method,
    )

    # Build species -> module mapping from the network nodes
    species_to_module: dict[str, int] = {}
    for node in network.get("nodes", []):
        species_to_module[node["id"]] = node["module"]

    # Build set of species that belong to the selected modules
    selected_module_set = set(module_ids)
    module_species = {
        sp for sp, mod in species_to_module.items() if mod in selected_module_set
    }

    # Filter and score each model
    filtered_models = []
    all_scores = []

    for idx, ind in enumerate(population):
        named = ind.get("named_features", {})
        if not named:
            continue

        feature_names = list(named.keys())
        total_features = len(feature_names)
        if total_features == 0:
            continue

        # Count features in selected modules
        in_module = [f for f in feature_names if f in module_species]
        in_module_count = len(in_module)
        module_coverage = in_module_count / total_features

        # Module coherence: fraction of features that are in the *same* module
        # (not just in selected modules — how many share one module)
        module_counts: dict[int, int] = {}
        for f in feature_names:
            mod = species_to_module.get(f)
            if mod is not None:
                module_counts[mod] = module_counts.get(mod, 0) + 1
        if module_counts:
            max_in_one_module = max(module_counts.values())
            coherence = max_in_one_module / total_features
        else:
            coherence = 0.0

        score_entry = {
            "index": idx,
            "module_coverage": round(module_coverage, 4),
            "module_coherence": round(coherence, 4),
            "features_in_module": in_module_count,
            "total_features": total_features,
            "in_module_features": in_module,
        }
        all_scores.append(score_entry)

        # Keep models with >= 50% features in the selected modules
        if module_coverage >= 0.5:
            model_summary = {
                "index": idx,
                "fit": ind.get("fit"),
                "auc": ind.get("auc") or ind.get("fit"),
                "accuracy": ind.get("accuracy"),
                "k": len(feature_names),
                "language": ind.get("language", ""),
                "data_type": ind.get("data_type", ""),
                "named_features": named,
                "module_coverage": round(module_coverage, 4),
                "module_coherence": round(coherence, 4),
                "features_in_module": in_module_count,
                "in_module_features": in_module,
            }
            filtered_models.append(model_summary)

    # Sort filtered models by module coverage descending, then by fit descending
    filtered_models.sort(
        key=lambda m: (m["module_coverage"], m.get("fit") or 0),
        reverse=True,
    )

    return {
        "total_models": len(population),
        "filtered_count": len(filtered_models),
        "selected_modules": module_ids,
        "module_species_count": len(module_species),
        "filtered_models": filtered_models,
        "coverage_threshold": 0.5,
    }


@router.post("/msp-annotations")
async def get_msp_annotations(
    body: dict,
    user: User = Depends(get_current_user),
):
    """Look up MSP taxonomic annotations for a list of feature names.

    Fetches from biobanks.gmt.bio with local caching.
    Body: {"features": ["msp_0001", "msp_0069", ...]}
    """
    feature_names = body.get("features", [])
    if not feature_names or not isinstance(feature_names, list):
        raise HTTPException(400, "Provide a 'features' list")
    annotations = msp_annotations.get_annotations(feature_names[:2000])
    return {"annotations": annotations}


@router.post("/{project_id}/enrichment")
async def compute_feature_enrichment(
    project_id: str,
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compute taxonomic/functional enrichment of a signature vs. background.

    Body: {
        "job_id": "...",
        "signature_level": "individual" | "fbm" | "jury",
        "model_index": 0,
        "annotation_type": "phylum" | "family" | "butyrate" | "inflammation" | "transit" | "oralisation"
    }
    """
    project = await get_project_with_access(project_id, user, db, require_role="viewer")
    if not project:
        raise HTTPException(404, "Project not found")

    job_id = body.get("job_id")
    signature_level = body.get("signature_level", "individual")
    model_index = body.get("model_index", 0)
    annotation_type = body.get("annotation_type", "phylum")

    if annotation_type not in ("phylum", "family", "butyrate", "inflammation", "transit", "oralisation"):
        raise HTTPException(400, f"Invalid annotation_type: {annotation_type}")
    if signature_level not in ("individual", "fbm", "jury"):
        raise HTTPException(400, f"Invalid signature_level: {signature_level}")

    results = storage.get_job_result(project_id, job_id)
    if not results:
        raise HTTPException(404, "Job results not found")

    feature_names = results.get("feature_names", [])
    population = results.get("population", [])
    sample_count = results.get("sample_count", len(population))

    # Extract signature features based on level
    if signature_level == "individual":
        if model_index < 0 or model_index >= len(population):
            raise HTTPException(400, f"model_index {model_index} out of range")
        sig_features = list(population[model_index].get("named_features", {}).keys())
    elif signature_level == "fbm":
        fbm_pop = enrichment.filter_fbm_python(population, sample_count)
        sig_features = list({
            feat for ind in fbm_pop
            for feat in ind.get("named_features", {}).keys()
        })
    elif signature_level == "jury":
        jury_data = results.get("jury")
        expert_count = jury_data.get("expert_count", 0) if jury_data else 0
        if expert_count <= 0:
            raise HTTPException(400, "No jury data available for this run")
        fbm_pop = enrichment.filter_fbm_python(population, sample_count)
        jury_experts = fbm_pop[:expert_count]
        sig_features = list({
            feat for ind in jury_experts
            for feat in ind.get("named_features", {}).keys()
        })
    else:
        sig_features = []

    if not sig_features:
        raise HTTPException(400, "No features found for the selected signature")

    # Fetch annotations for all background features
    annotations = msp_annotations.get_annotations(feature_names)

    result = enrichment.compute_enrichment(
        signature_features=sig_features,
        background_features=feature_names,
        annotations=annotations,
        annotation_type=annotation_type,
    )
    result["signature_level"] = signature_level
    return result


@router.get("/{project_id}/insights/{job_id}")
async def get_experiment_insights(
    project_id: str,
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compute automated insights for a completed experiment.

    Synthesizes findings across performance, robustness, biology, jury,
    and generates actionable recommendations.
    """
    project = await get_project_with_access(project_id, user, db, require_role="viewer")
    if not project:
        raise HTTPException(404, "Project not found")

    results = storage.get_job_result(project_id, job_id)
    if not results:
        raise HTTPException(404, "Job results not found")

    feature_names = results.get("feature_names", [])
    population = results.get("population", [])

    # Fetch MSP annotations for biological context
    annotations = msp_annotations.get_annotations(feature_names)

    # Run phylum enrichment on best model automatically
    enrichment_results = None
    if population:
        sig_features = list(population[0].get("named_features", {}).keys())
        if sig_features:
            try:
                enrichment_results = enrichment.compute_enrichment(
                    signature_features=sig_features,
                    background_features=feature_names,
                    annotations=annotations,
                    annotation_type="phylum",
                )
            except Exception:
                pass  # enrichment is optional for insights

    # Load job config for recommendation context
    from ..models.db_models import Job
    from sqlalchemy import select
    job_config = None
    stmt = select(Job).where(Job.id == job_id, Job.project_id == project_id)
    result_row = await db.execute(stmt)
    job = result_row.scalar_one_or_none()
    if job and job.config:
        job_config = job.config

    return insights_service.compute_insights(
        results=results,
        annotations=annotations,
        enrichment_results=enrichment_results,
        job_config=job_config,
    )
