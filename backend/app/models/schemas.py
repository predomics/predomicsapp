"""Pydantic schemas for API request/response models."""

from __future__ import annotations
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
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
    seed: int = 42
    thread_number: int = 4
    k_penalty: float = 0.0001
    cv: bool = False
    gpu: bool = False
    display_colorful: bool = True
    # Advanced
    epsilon: Optional[float] = None
    fr_penalty: Optional[float] = None
    bias_penalty: Optional[float] = None
    threshold_ci_n_bootstrap: Optional[int] = None
    threshold_ci_penalty: Optional[float] = None
    threshold_ci_alpha: Optional[float] = None
    threshold_ci_frac_bootstrap: Optional[float] = None
    user_feature_penalties_weight: Optional[float] = None
    n_model_to_display: Optional[int] = None


class GaParams(BaseModel):
    population_size: int = 5000
    max_epochs: int = 200
    min_epochs: int = 10
    max_age_best_model: int = 10
    k_min: int = 1
    k_max: int = 200
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
    k_start: int = 1
    k_stop: int = 100
    best_models_criterion: float = 10.0
    max_nb_of_models: int = 10000


class McmcParams(BaseModel):
    n_iter: int = 1000
    n_burn: int = 500
    lambda_: float = Field(0.001, alias="lambda")
    nmin: int = 10


class LassoParams(BaseModel):
    alpha_min: float = 0.001
    alpha_max: float = 1.0
    n_alphas: int = 100
    l1_ratio: float = 1.0

class IlsParams(BaseModel):
    max_iterations: int = 100
    perturbation_size: int = 3
    local_search_steps: int = 50
    max_no_improve: int = 20
    k_min: int = 1
    k_max: int = 50

class SaParams(BaseModel):
    initial_temperature: float = 1.0
    cooling_rate: float = 0.999
    min_temperature: float = 0.001
    max_iterations: int = 10000
    snapshot_interval: int = 100
    k_min: int = 1
    k_max: int = 50


class AcoParams(BaseModel):
    n_ants: int = 100
    max_iterations: int = 200
    min_iterations: int = 10
    alpha: float = 1.0
    beta: float = 2.0
    rho: float = 0.1
    tau_min: float = 0.01
    tau_max: float = 1.0
    elite_weight: float = 2.0
    k_min: int = 1
    k_max: int = 200
    max_age_best_model: int = 10


class RfParams(BaseModel):
    n_estimators: int = 100
    max_depth: Optional[int] = None
    min_samples_split: int = 2


class SvmParams(BaseModel):
    kernel: str = "linear"
    C: float = 1.0


class LogisticParams(BaseModel):
    penalty: str = "l1"
    C: float = 1.0
    l1_ratio: Optional[float] = None
    max_iter: int = 1000


class XgboostParams(BaseModel):
    n_estimators: int = 100
    max_depth: int = 6
    learning_rate: float = 0.1


class LightgbmParams(BaseModel):
    n_estimators: int = 100
    max_depth: int = -1
    learning_rate: float = 0.1


class ExtraTreesParams(BaseModel):
    n_estimators: int = 100
    max_depth: Optional[int] = None


class AdaboostParams(BaseModel):
    n_estimators: int = 50
    learning_rate: float = 1.0


class KnnParams(BaseModel):
    n_neighbors: int = 5
    weights: str = "uniform"


class ClinicalParams(BaseModel):
    enabled: bool = False
    method: str = "stacking"
    interactions: bool = False
    columns: str = ""


class DataConfig(BaseModel):
    features_in_rows: bool = True
    inverse_classes: bool = False
    holdout_ratio: float = 0.20
    feature_minimal_prevalence_pct: int = 10
    feature_selection_method: str = "wilcoxon"
    feature_maximal_adj_pvalue: float = 0.05
    feature_minimal_feature_value: float = 0.0
    classes: Optional[List[str]] = None


class CvParams(BaseModel):
    outer_folds: int = 5
    inner_folds: int = 5
    overfit_penalty: float = 0.0
    # Advanced
    resampling_inner_folds_epochs: Optional[int] = None
    fit_on_valid: Optional[bool] = None
    cv_best_models_ci_alpha: Optional[float] = None
    stratify_by: Optional[str] = None


class ImportanceParams(BaseModel):
    compute_importance: bool = False
    n_permutations_mda: int = 100
    scaled_importance: bool = True
    importance_aggregation: str = "mean"


class VotingParams(BaseModel):
    vote: bool = False
    fbm_ci_alpha: float = 0.05
    prune_before_voting: bool = False
    min_experts: int = 0
    max_experts: int = 0
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
    max_total_memory_mb: int = 256
    max_buffer_size_mb: int = 128


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


class BatchSweepConfig(BaseModel):
    """Define parameter sweeps for batch runs."""
    sweeps: Dict[str, list] = {}   # "ga.population_size": [1000, 5000, 10000]


class ExperimentDetail(ExperimentSummary):
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


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    gpredomicspy_available: bool = False
    scitq_enabled: bool = False
    scitq_server: Optional[str] = None


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
