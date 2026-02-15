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


class FitFunction(str, Enum):
    auc = "auc"
    specificity = "specificity"
    sensitivity = "sensitivity"
    mcc = "mcc"
    f1_score = "f1_score"
    g_mean = "g_mean"


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
    n_iter: int = 10000
    n_burn: int = 5000
    lambda_: float = Field(0.001, alias="lambda")
    nmin: int = 10


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
    data: DataConfig = DataConfig()
    cv: CvParams = CvParams()
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
    files: list[DatasetFileRef] = []
    created_at: str = ""
    project_count: int = 0


class ProjectInfo(BaseModel):
    project_id: str
    name: str
    description: str = ""
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
