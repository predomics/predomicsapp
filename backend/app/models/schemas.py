"""Pydantic schemas for API request/response models."""

from __future__ import annotations
from typing import Any, Optional, List, Dict
from pydantic import BaseModel, Field, model_validator
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Algorithm(str, Enum):
    ga = "ga"
    beam = "beam"
    mcmc = "mcmc"
    aco = "aco"
    sa = "sa"
    lasso = "lasso"
    ils = "ils"
    rf = "rf"
    svm = "svm"
    logistic = "logistic"
    xgboost = "xgboost"
    lightgbm = "lightgbm"
    extra_trees = "extra_trees"
    adaboost = "adaboost"
    knn = "knn"


class FitFunction(str, Enum):
    auc = "auc"
    specificity = "specificity"
    sensitivity = "sensitivity"
    mcc = "mcc"
    f1_score = "f1_score"
    g_mean = "g_mean"
    # Regression fit functions
    spearman = "spearman"
    pearson = "pearson"
    rmse = "rmse"
    mutual_information = "mutual_information"


REGRESSION_FIT_FUNCTIONS = {"spearman", "pearson", "rmse", "mutual_information"}


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


# ---------------------------------------------------------------------------
# Parameter schemas
# ---------------------------------------------------------------------------

class GeneralParams(BaseModel):
    algo: Algorithm = Algorithm.ga
    language: str = "bin,ter,ratio"
    data_type: str = "raw,prev"
    fit: FitFunction = FitFunction.auc
    seed: int = Field(42, ge=0)
    thread_number: int = Field(4, ge=1, le=1024)  # capped server-side to the CPUs available
    k_penalty: float = Field(0.0001, ge=0)
    cv: bool = False
    gpu: bool = False
    display_colorful: bool = True
    # Advanced
    epsilon: Optional[float] = Field(None, gt=0)
    fr_penalty: Optional[float] = None
    bias_penalty: Optional[float] = None
    threshold_ci_n_bootstrap: Optional[int] = Field(None, ge=0, le=100000)
    threshold_ci_penalty: Optional[float] = None
    threshold_ci_alpha: Optional[float] = None
    threshold_ci_frac_bootstrap: Optional[float] = None
    user_feature_penalties_weight: Optional[float] = None
    n_model_to_display: Optional[int] = Field(None, ge=0, le=100000)


class GaParams(BaseModel):
    population_size: int = Field(5000, ge=1, le=1000000)
    max_epochs: int = Field(200, ge=1, le=1000000)
    min_epochs: int = Field(10, ge=0, le=1000000)
    max_age_best_model: int = Field(10, ge=0, le=1000000)
    k_min: int = Field(1, ge=1, le=100000)
    k_max: int = Field(200, ge=1, le=100000)
    # Advanced
    select_elite_pct: Optional[float] = None
    select_niche_pct: Optional[float] = None
    select_random_pct: Optional[float] = None
    mutated_children_pct: Optional[float] = None
    mutated_features_pct: Optional[float] = None
    mutation_non_null_chance_pct: Optional[float] = None
    forced_diversity_pct: Optional[float] = None
    forced_diversity_epochs: Optional[int] = None
    random_sampling_pct: Optional[float] = None
    random_sampling_epochs: Optional[int] = None
    n_epochs_before_global: Optional[int] = None


class BeamParams(BaseModel):
    method: Optional[str] = None
    k_start: int = Field(1, ge=1, le=100000)
    k_stop: int = Field(100, ge=1, le=100000)
    best_models_criterion: float = 10.0
    max_nb_of_models: int = Field(10000, ge=1, le=10000000)
    # OR (clause) languages only: maximum number of features per clause (0 = unlimited)
    max_clause_size: int = Field(3, ge=0, le=100000)


class McmcParams(BaseModel):
    n_iter: int = Field(1000, ge=1, le=10000000)
    n_burn: int = Field(500, ge=0, le=10000000)
    lambda_: float = Field(0.001, alias="lambda")
    nmin: int = Field(10, ge=0, le=100000)


class LassoParams(BaseModel):
    alpha_min: float = 0.001
    alpha_max: float = 1.0
    n_alphas: int = Field(100, ge=1, le=100000)
    l1_ratio: float = 1.0

class IlsParams(BaseModel):
    max_iterations: int = Field(100, ge=1, le=10000000)
    perturbation_size: int = 3
    local_search_steps: int = Field(50, ge=1, le=10000000)
    max_no_improve: int = 20
    k_min: int = Field(1, ge=1, le=100000)
    k_max: int = Field(50, ge=1, le=100000)

class SaParams(BaseModel):
    initial_temperature: float = 1.0
    cooling_rate: float = 0.999
    min_temperature: float = 0.001
    max_iterations: int = Field(10000, ge=1, le=100000000)
    snapshot_interval: int = Field(100, ge=1, le=100000000)
    k_min: int = Field(1, ge=1, le=100000)
    k_max: int = Field(50, ge=1, le=100000)


class AcoParams(BaseModel):
    n_ants: int = Field(100, ge=1, le=1000000)
    max_iterations: int = Field(200, ge=1, le=10000000)
    min_iterations: int = Field(10, ge=0, le=10000000)
    alpha: float = 1.0
    beta: float = 2.0
    rho: float = 0.1
    tau_min: float = 0.01
    tau_max: float = 1.0
    elite_weight: float = 2.0
    k_min: int = Field(1, ge=1, le=100000)
    k_max: int = Field(200, ge=1, le=100000)
    max_age_best_model: int = 10


class RfParams(BaseModel):
    n_estimators: int = Field(100, ge=1, le=100000)
    max_depth: Optional[int] = None
    min_samples_split: int = 2


class SvmParams(BaseModel):
    kernel: str = "linear"
    C: float = 1.0


class LogisticParams(BaseModel):
    penalty: str = "l1"
    C: float = 1.0
    l1_ratio: Optional[float] = None
    max_iter: int = Field(1000, ge=1, le=10000000)


class XgboostParams(BaseModel):
    n_estimators: int = Field(100, ge=1, le=100000)
    max_depth: int = 6
    learning_rate: float = 0.1


class LightgbmParams(BaseModel):
    n_estimators: int = Field(100, ge=1, le=100000)
    max_depth: int = -1
    learning_rate: float = 0.1


class ExtraTreesParams(BaseModel):
    n_estimators: int = Field(100, ge=1, le=100000)
    max_depth: Optional[int] = None


class AdaboostParams(BaseModel):
    n_estimators: int = Field(50, ge=1, le=100000)
    learning_rate: float = 1.0


class KnnParams(BaseModel):
    n_neighbors: int = Field(5, ge=1, le=100000)
    weights: str = "uniform"


class ClinicalParams(BaseModel):
    enabled: bool = False
    method: str = "stacking"
    interactions: bool = False
    columns: str = ""


class DataConfig(BaseModel):
    features_in_rows: bool = True
    inverse_classes: bool = False
    holdout_ratio: float = Field(0.20, ge=0, lt=1)
    feature_minimal_prevalence_pct: int = Field(10, ge=0, le=100)
    feature_selection_method: str = "wilcoxon"
    feature_maximal_adj_pvalue: float = Field(0.05, ge=0, le=1)
    feature_minimal_feature_value: float = 0.0
    classes: Optional[List[str]] = None


class CvParams(BaseModel):
    outer_folds: int = Field(5, ge=2, le=100)
    inner_folds: int = Field(5, ge=2, le=100)
    overfit_penalty: float = 0.0
    # Advanced
    resampling_inner_folds_epochs: Optional[int] = None
    fit_on_valid: Optional[bool] = None
    cv_best_models_ci_alpha: Optional[float] = None
    stratify_by: Optional[str] = None


class ImportanceParams(BaseModel):
    compute_importance: bool = False
    n_permutations_mda: int = Field(100, ge=1, le=100000)
    scaled_importance: bool = True
    importance_aggregation: str = "mean"


class VotingParams(BaseModel):
    vote: bool = False
    fbm_ci_alpha: float = 0.05
    prune_before_voting: bool = False
    min_experts: int = Field(0, ge=0, le=1000000)
    max_experts: int = Field(0, ge=0, le=1000000)
    # Advanced
    min_perf: Optional[float] = None
    min_diversity: Optional[int] = None
    method: Optional[str] = None
    method_threshold: Optional[float] = None
    threshold_windows_pct: Optional[float] = None
    complete_display: Optional[bool] = None


class GpuParams(BaseModel):
    fallback_to_cpu: bool = True
    memory_policy: str = "Strict"
    max_total_memory_mb: int = Field(256, ge=1, le=1048576)
    max_buffer_size_mb: int = Field(128, ge=1, le=1048576)


# OR (clause) languages of gpredomics: accepted spellings, and the one that is
# reserved but not implemented by the engine.
OR_LANGUAGE_ALIASES = frozenset({
    "bin-or", "bin_or", "binary-or", "binary_or", "0-or",
    "ter-or", "ter_or", "ternary-or", "ternary_or", "1-or",
    "ratio-or", "ratio_or", "3-or",
})
RESERVED_LANGUAGE_ALIASES = frozenset({"pow2-or", "pow2_or", "2-or"})


def or_languages_in(language: str) -> list[str]:
    """The OR languages named in a comma-separated ``general.language`` value."""
    return [v.strip().lower() for v in str(language or "").split(",")
            if v.strip().lower() in OR_LANGUAGE_ALIASES]


class RunConfig(BaseModel):
    """Full configuration for a gpredomics run."""
    general: GeneralParams = GeneralParams()
    ga: GaParams = GaParams()
    beam: BeamParams = BeamParams()
    mcmc: McmcParams = McmcParams()
    aco: AcoParams = AcoParams()
    sa: SaParams = SaParams()
    lasso: LassoParams = LassoParams()
    ils: IlsParams = IlsParams()
    rf: RfParams = RfParams()
    svm: SvmParams = SvmParams()
    logistic: LogisticParams = LogisticParams()
    xgboost: XgboostParams = XgboostParams()
    lightgbm: LightgbmParams = LightgbmParams()
    extra_trees: ExtraTreesParams = ExtraTreesParams()
    adaboost: AdaboostParams = AdaboostParams()
    knn: KnnParams = KnnParams()
    data: DataConfig = DataConfig()
    cv: CvParams = CvParams()
    clinical: ClinicalParams = ClinicalParams()
    importance: ImportanceParams = ImportanceParams()
    voting: VotingParams = VotingParams()
    gpu: GpuParams = GpuParams()

    @model_validator(mode="after")
    def _or_languages_need_beam(self):
        """The engine only grows clause models with Beam; refuse the rest up front."""
        picked = [v.strip().lower() for v in str(self.general.language or "").split(",") if v.strip()]
        reserved = [v for v in picked if v in RESERVED_LANGUAGE_ALIASES]
        if reserved:
            raise ValueError(
                f"Language '{reserved[0]}' (Pow2-OR) is reserved but not implemented by the engine."
            )
        algo = self.general.algo.value if hasattr(self.general.algo, "value") else str(self.general.algo)
        or_langs = or_languages_in(self.general.language)
        if or_langs and algo != "beam":
            raise ValueError(
                f"OR languages ({', '.join(or_langs)}) are only available with the Beam algorithm "
                f"(general.algo = beam), not with '{algo}'."
            )
        return self


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class IndividualResponse(BaseModel):
    k: int
    auc: float
    fit: float
    accuracy: float
    sensitivity: float
    specificity: float
    threshold: float
    language: str
    data_type: str
    epoch: int
    features: dict[int, int]  # feature_index -> coefficient sign
    clauses: Optional[List[List[int]]] = None  # OR languages: feature indices per clause


class PopulationResponse(BaseModel):
    size: int
    individuals: list[IndividualResponse]


class ExperimentSummary(BaseModel):
    job_id: str
    name: Optional[str] = None
    status: JobStatus
    fold_count: int = 0
    generation_count: int = 0
    execution_time: float = 0.0
    feature_count: int = 0
    sample_count: int = 0
    best_auc: Optional[float] = None
    best_k: Optional[int] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    config_summary: Optional[str] = None
    user_name: Optional[str] = None
    language: Optional[str] = None
    data_type: Optional[str] = None
    population_size: Optional[int] = None
    config_hash: Optional[str] = None
    disk_size_bytes: Optional[int] = None
    batch_id: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    mock: Optional[bool] = None  # True when results were fabricated by the mock engine


class BatchSweepConfig(BaseModel):
    """Define parameter sweeps for batch runs."""
    sweeps: Dict[str, list] = {}   # "ga.population_size": [1000, 5000, 10000]


class FbmModuleFilterRequest(BaseModel):
    """Body of POST /data-explore/{project_id}/fbm-module-filter."""
    job_id: str = Field(min_length=1, max_length=64)
    module_ids: List[int] = Field(min_length=1, max_length=10000)
    min_prevalence_pct: float = Field(30.0, ge=0, le=100)
    correlation_threshold: float = Field(0.3, ge=0, le=1)
    community_method: str = "louvain"
    features_in_rows: Optional[bool] = None


class MspAnnotationsRequest(BaseModel):
    """Body of POST /data-explore/msp-annotations."""
    features: List[str] = Field(min_length=1, max_length=5000)


class EnrichmentRequest(BaseModel):
    """Body of POST /data-explore/{project_id}/enrichment."""
    job_id: str = Field(min_length=1, max_length=64)
    signature_level: str = "individual"
    model_index: int = Field(0, ge=0)
    annotation_type: str = "phylum"


class ExperimentDetail(ExperimentSummary):
    best_auc_test: Optional[float] = None  # AUC of the best model on the held-out test set, when there is one
    feature_names: list[str] = []
    sample_names: list[str] = []
    best_individual: Optional[IndividualResponse] = None


class DatasetInfo(BaseModel):
    filename: str
    n_features: int
    n_samples: int
    n_classes: int
    class_labels: list[str] = []
    features_in_rows: bool = True


class DatasetFileRef(BaseModel):
    """A single file within a composite dataset."""
    id: str
    filename: str
    role: Optional[str] = None


class DatasetRef(BaseModel):
    """A composite dataset with its files, as seen from a project."""
    id: str
    name: str
    files: list[DatasetFileRef] = []


class DatasetResponse(BaseModel):
    """Full dataset info for the dataset library."""
    id: str
    name: str
    description: str = ""
    tags: list[str] = []
    archived: bool = False
    files: list[DatasetFileRef] = []
    created_at: str = ""
    project_count: int = 0
    metadata: Optional[dict] = None


class DatasetUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class YFromMetadataRequest(BaseModel):
    """Request to generate a y file from a metadata column."""
    column: str
    file_role: str = "ytrain"


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    class_names: Optional[dict] = None


class ProjectInfo(BaseModel):
    project_id: str
    name: str
    description: str = ""
    class_names: Optional[dict] = None
    archived: bool = False
    created_at: str
    updated_at: Optional[str] = None
    datasets: list[DatasetRef] = []
    jobs: list[str] = []
    job_count: int = 0
    share_count: int = 0
    latest_job_status: Optional[str] = None


# ---------------------------------------------------------------------------
# Data Explore schemas
# ---------------------------------------------------------------------------

class DataSummaryResponse(BaseModel):
    n_features: int
    n_samples: int
    n_classes: int
    class_labels: list[str] = []
    class_counts: dict[str, int] = {}


class FeatureStatRow(BaseModel):
    name: str
    index: int
    selected: bool
    feature_class: int  # 0, 1, or 2 (not significant)
    significance: Optional[float] = None
    mean: float
    std: float
    prevalence: float
    mean_0: Optional[float] = None
    mean_1: Optional[float] = None
    std_0: Optional[float] = None
    std_1: Optional[float] = None
    prevalence_0: Optional[float] = None
    prevalence_1: Optional[float] = None


class HistogramData(BaseModel):
    bin_edges: list[float]
    counts: list[int]


class DistributionsResponse(BaseModel):
    prevalence_histogram: HistogramData
    sd_histogram: HistogramData
    class_distribution: dict[str, int]


class BoxplotClassData(BaseModel):
    min: float
    q1: float
    median: float
    q3: float
    max: float
    mean: float
    n: int


class FeatureAbundanceItem(BaseModel):
    name: str
    classes: dict[str, BoxplotClassData]
    significance: Optional[float] = None


# ===========================================================================
# Response models (documentation of what the API returns)
# ===========================================================================
#
# These describe the JSON the endpoints already produce; they must never change
# it. Every model therefore allows extra keys (analysis services add fields over
# time) and the routes use ``response_model_exclude_unset=True`` so that a key the
# handler did not return is not invented as ``null``. Nested rows whose keys vary
# with the algorithm or the data stay ``dict[str, Any]``.

class ApiModel(BaseModel):
    model_config = {"extra": "allow"}


class Detail(ApiModel):
    """A plain confirmation message."""
    detail: str


# --- analysis ---------------------------------------------------------------

class BatchJobRef(ApiModel):
    job_id: str
    name: Optional[str] = None


class BatchLaunch(ApiModel):
    """Jobs created by one batch (parameter sweep) request."""
    batch_id: str
    job_count: int
    jobs: List[BatchJobRef]


class BatchSummary(ApiModel):
    batch_id: str
    job_count: int
    completed: int
    failed: int
    running: int = Field(description="Jobs still pending or running")
    best_auc: Optional[float] = None
    best_job_id: Optional[str] = None
    created_at: Optional[str] = None


class DuplicateGroup(ApiModel):
    """Jobs of a project that were launched with the same configuration and data."""
    config_hash: Optional[str] = None
    config_summary: Optional[str] = None
    jobs: List[Dict[str, Any]]


class JobConfigResponse(ApiModel):
    job_id: str
    name: Optional[str] = None
    config: Dict[str, Any]


class JobLogs(ApiModel):
    """A chunk of the job's console output. Pass ``next_offset`` back to get only what is new."""
    job_id: str
    status: str
    log: str
    size: int = Field(description="Total size of the log file in bytes")
    offset: int
    next_offset: int
    truncated: bool = Field(description="True when only the tail of a large log was returned")


class JobProgress(ApiModel):
    max_gen: int = Field(description="Planned number of generations (0 when unknown)")
    points: List[Dict[str, Any]] = Field(description="One entry per reported generation: generation, k, language, elapsed")


class JobResults(ApiModel):
    """Complete results of a job, as written by the engine worker (``results.json``)."""
    engine: Optional[str] = None
    mock: Optional[bool] = Field(None, description="True when produced without the real engine (tests/dev)")
    feature_names: Optional[List[str]] = None
    sample_names: Optional[List[str]] = None
    best_individual: Optional[Dict[str, Any]] = None
    population: Optional[List[Dict[str, Any]]] = None
    population_size: Optional[int] = None
    generation_tracking: Optional[List[Dict[str, Any]]] = None
    generation_count: Optional[int] = None
    fold_count: Optional[int] = None
    execution_time: Optional[float] = None


class StabilityAnalysis(ApiModel):
    stability_by_k: Optional[Any] = None
    dendrogram: Optional[Any] = None
    feature_sparsity_heatmap: Optional[Any] = None
    stats: Optional[Any] = None


class ValidationResult(ApiModel):
    """Scores of a trained model on newly uploaded samples."""
    sample_names: Optional[List[str]] = None
    scores: Optional[List[Optional[float]]] = None
    predicted_classes: Optional[List[Optional[int]]] = None
    threshold: Optional[float] = None
    matched_features: Optional[List[str]] = None
    missing_features: Optional[List[str]] = None
    n_samples: Optional[int] = None
    evaluation: Optional[Dict[str, Any]] = Field(None, description="Present when class labels were supplied")


# --- dashboard --------------------------------------------------------------

class DashboardResponse(ApiModel):
    projects: int
    shared_with_me: int
    datasets: int
    running_jobs: int
    pending_jobs: int
    completed_jobs: int
    failed_jobs: int
    active_jobs: List[Dict[str, Any]]
    recent_completions: List[Dict[str, Any]]
    activity: List[Dict[str, Any]]


# --- data exploration -------------------------------------------------------

class DataSummary(ApiModel):
    n_features: int
    n_samples: int
    n_classes: int
    class_labels: List[Any]
    class_counts: Dict[str, int]


class FeatureStatsResponse(ApiModel):
    features: List[Dict[str, Any]] = Field(description="Per feature: name, prevalence, means, significance, selected…")
    selected_count: int
    method: str
    n_features: int


class Histogram(ApiModel):
    bin_edges: List[float]
    counts: List[int]


class DistributionsResponse(ApiModel):
    prevalence_histogram: Optional[Histogram] = None
    sd_histogram: Optional[Histogram] = None
    class_distribution: Optional[Dict[str, int]] = None


class FeatureAbundanceResponse(ApiModel):
    features: List[Dict[str, Any]]
    transform: Optional[str] = None


class BarcodeData(ApiModel):
    matrix: List[List[Optional[float]]]
    feature_names: List[str]
    sample_names: List[str]
    sample_classes: List[Any]
    class_labels: List[Any]
    class_boundaries: List[int]
    zero_mask: Optional[Any] = None
    transform: Optional[str] = None


class ClassHeatmap(ApiModel):
    matrix: List[List[Optional[float]]]
    feature_names: List[str]
    class_labels: List[Any]
    transform: Optional[str] = None


class OrdinationResponse(ApiModel):
    """PCoA, t-SNE or UMAP coordinates of the samples, with class ellipses and PERMANOVA."""
    coords: Optional[Any] = None
    sample_names: Optional[List[str]] = None
    sample_classes: Optional[List[Any]] = None
    class_labels: Optional[List[Any]] = None
    variance_explained: Optional[Any] = None
    metric: Optional[str] = None
    n_samples: Optional[int] = None
    n_features_used: Optional[int] = None
    ellipses: Optional[Any] = None
    permanova: Optional[Any] = None
    method: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


class NetworkResponse(ApiModel):
    """A feature network: nodes, edges and, for co-abundance, modules and statistics."""
    nodes: Optional[List[Dict[str, Any]]] = None
    edges: Optional[List[Dict[str, Any]]] = None
    modules: Optional[List[Dict[str, Any]]] = None
    taxonomy_legend: Optional[List[Dict[str, Any]]] = None
    stats: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class DualNetworkResponse(ApiModel):
    """One co-abundance network per class, and how they differ."""
    network_0: Optional[Dict[str, Any]] = None
    network_1: Optional[Dict[str, Any]] = None
    comparison: Optional[Any] = None
    sankey_links: Optional[Any] = None


class AberrantCorrelations(ApiModel):
    pairs: List[Dict[str, Any]]
    n_features: Optional[int] = None
    n_pairs: Optional[int] = None
    feature_names: Optional[List[str]] = None


class NetworkInfo(ApiModel):
    id: str
    name: Optional[str] = None
    n_nodes: Optional[int] = None
    n_edges: Optional[int] = None
    filename: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None


class DeletedFlag(ApiModel):
    deleted: bool


class FbmModuleFilterResponse(ApiModel):
    total_models: Optional[int] = None
    filtered_count: Optional[int] = None
    selected_modules: Optional[List[Any]] = None
    module_species_count: Optional[Any] = None
    filtered_models: Optional[List[Dict[str, Any]]] = None
    coverage_threshold: Optional[float] = None


class MspAnnotationsResponse(ApiModel):
    annotations: Dict[str, Dict[str, Any]] = Field(description="Feature name → taxonomy and functional annotation")


class EnrichmentResponse(ApiModel):
    annotation_type: Optional[str] = None
    signature_size: Optional[int] = None
    background_size: Optional[int] = None
    annotated_signature: Optional[int] = None
    annotated_background: Optional[int] = None
    results: Optional[List[Dict[str, Any]]] = None


class InsightsResponse(ApiModel):
    insights: Optional[List[Dict[str, Any]]] = None
    scores: Optional[Dict[str, Any]] = None
    summary: Optional[Any] = None
    # True while feature taxonomy is still being fetched: biological insights are partial.
    annotations_pending: Optional[bool] = None


# --- meta-analysis ----------------------------------------------------------

class SearchableJob(ApiModel):
    job_id: str
    project_id: str
    project_name: Optional[str] = None
    job_name: Optional[str] = None
    best_auc: Optional[float] = None
    best_k: Optional[int] = None
    language: Optional[str] = None
    completed_at: Optional[str] = None


class MetaComparison(ApiModel):
    jobs: List[Dict[str, Any]]
    feature_overlap: Dict[str, List[str]] = Field(description="Feature name → ids of the jobs whose best model uses it")
    concordance: Dict[str, Dict[str, Any]]
    meta_auc: Optional[float] = None


# --- public links -----------------------------------------------------------

class PublicLink(ApiModel):
    id: str
    token: str
    expires_at: Optional[str] = None
    created_at: Optional[str] = None
    is_active: bool


class PublicProject(ApiModel):
    project: Dict[str, Any] = Field(description="name and description")
    jobs: List[Dict[str, Any]] = Field(description="Completed jobs: job_id, name, best_auc, best_k, completed_at")


# --- webhooks ---------------------------------------------------------------

class WebhookInfo(ApiModel):
    id: str
    name: str
    url: str
    events: Optional[List[str]] = None
    is_active: Optional[bool] = None
    created_at: Optional[str] = None
    secret: Optional[str] = Field(None, description="Signing secret; returned only when the webhook is created")


class StatusResponse(ApiModel):
    status: str


# --- signature zoo ----------------------------------------------------------

class SignatureComparison(ApiModel):
    signatures: List[Dict[str, Any]]
    common_features: List[str]
    unique_features: Dict[str, List[str]]
    feature_presence: Dict[str, List[str]]
    overlap_matrix: List[List[Any]]
    performance_comparison: List[Dict[str, Any]]


class SignatureDeleted(ApiModel):
    status: str
    id: str
