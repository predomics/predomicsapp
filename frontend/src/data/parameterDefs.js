/**
 * Parameter definitions for gpredomics — single source of truth.
 *
 * Descriptions from gpredomics/param.yaml, defaults from gpredomics/src/param.rs.
 * Used by:
 *  - stores/config.js  → builds reactive form defaults
 *  - ParametersTab.vue  → data-driven rendering + info bubbles
 */

export const CATEGORIES = [
  { id: 'general', label: 'General', colorVar: '--cat-general' },
  { id: 'ga', label: 'Genetic Algorithm', colorVar: '--cat-ga', algoFilter: 'ga' },
  { id: 'beam', label: 'Beam Search', colorVar: '--cat-beam', algoFilter: 'beam' },
  { id: 'mcmc', label: 'MCMC', colorVar: '--cat-mcmc', algoFilter: 'mcmc' },
  { id: 'cv', label: 'Cross-Validation', colorVar: '--cat-cv', enabledBy: 'general.cv' },
  { id: 'importance', label: 'Feature Importance', colorVar: '--cat-importance' },
  { id: 'voting', label: 'Voting Ensemble', colorVar: '--cat-voting' },
  { id: 'gpu', label: 'GPU Settings', colorVar: '--cat-gpu', enabledBy: 'general.gpu' },
]

export const PARAM_DEFS = [
  // ===================== GENERAL (18) =====================
  {
    key: 'algo', label: 'Algorithm', category: 'general', level: 'basic', inputType: 'select', defaultValue: 'ga',
    description: 'Optimization algorithm: GA (Genetic Algorithm), Beam (Beam Search), or MCMC (Markov Chain Monte Carlo).',
    options: [{ value: 'ga', label: 'Genetic Algorithm' }, { value: 'beam', label: 'Beam Search' }, { value: 'mcmc', label: 'MCMC' }],
  },
  {
    key: 'fit', label: 'Fit function', category: 'general', level: 'basic', inputType: 'select', defaultValue: 'auc',
    description: 'Objective metric for model evaluation. AUC is recommended for balanced classification.',
    options: [
      { value: 'auc', label: 'AUC' }, { value: 'mcc', label: 'MCC' }, { value: 'f1_score', label: 'F1 Score' },
      { value: 'sensitivity', label: 'Sensitivity' }, { value: 'specificity', label: 'Specificity' },
      { value: 'g_mean', label: 'Geometric Mean' }, { value: 'npv', label: 'NPV' }, { value: 'ppv', label: 'PPV' },
    ],
  },
  {
    key: 'language', label: 'Language', category: 'general', level: 'basic', inputType: 'text', defaultValue: 'bin,ter,ratio',
    description: 'Model languages: bin (binary), ter (ternary), ratio, pow2. Comma-separated list; initial population is split among them.',
  },
  {
    key: 'data_type', label: 'Data type', category: 'general', level: 'basic', inputType: 'text', defaultValue: 'raw,prev',
    description: 'Data transformations: raw, prev (prevalence), log. Comma-separated list accepted.',
  },
  {
    key: 'seed', label: 'Random seed', category: 'general', level: 'basic', inputType: 'number', defaultValue: 42,
    description: 'Seed for reproducibility. Used in parent selection, crossover and mutation.', min: 0, step: 1,
  },
  {
    key: 'thread_number', label: 'Threads', category: 'general', level: 'basic', inputType: 'number', defaultValue: 4,
    description: 'Number of CPU threads for feature selection and fit computation.', min: 1, max: 64, step: 1,
  },
  {
    key: 'cv', label: 'Cross-validation', category: 'general', level: 'basic', inputType: 'checkbox', defaultValue: false,
    description: 'Enable cross-validation for more robust model evaluation.',
  },
  {
    key: 'gpu', label: 'GPU acceleration', category: 'general', level: 'basic', inputType: 'checkbox', defaultValue: false,
    description: 'Use GPU for fitness computation (GA and Beam only). Uses f32 precision.',
  },
  // General advanced
  {
    key: 'epsilon', label: 'Epsilon', category: 'general', level: 'advanced', inputType: 'number', defaultValue: 1e-5,
    description: 'Threshold for prevalence data type, or replacement value below threshold for log data type.', min: 0, step: 1e-6,
  },
  {
    key: 'k_penalty', label: 'k penalty', category: 'general', level: 'advanced', inputType: 'number', defaultValue: 0.0001,
    description: 'Penalty multiplied by k (number of variables). Encourages parsimonious models.', min: 0, step: 0.0001,
  },
  {
    key: 'fr_penalty', label: 'FR penalty', category: 'general', level: 'advanced', inputType: 'number', defaultValue: 0.0,
    description: 'Used when fit is specificity or sensitivity. Subtracts (1 - symmetrical_metric) * fr_penalty.', min: 0, step: 0.01,
  },
  {
    key: 'bias_penalty', label: 'Bias penalty', category: 'general', level: 'advanced', inputType: 'number', defaultValue: 0.0,
    description: 'Penalizes model fit when specificity or sensitivity falls below 0.5.', min: 0, step: 0.01,
  },
  {
    key: 'threshold_ci_n_bootstrap', label: 'Bootstrap samples (CI)', category: 'general', level: 'advanced', inputType: 'number', defaultValue: 0,
    description: 'Number of bootstrap samples for threshold confidence interval. 0 = disabled.', min: 0, step: 100,
  },
  {
    key: 'threshold_ci_penalty', label: 'CI penalty', category: 'general', level: 'advanced', inputType: 'number', defaultValue: 0.5,
    description: 'If threshold CI exists, penalizes evolution: rejection_rate * penalty.', min: 0, max: 1, step: 0.05,
  },
  {
    key: 'threshold_ci_alpha', label: 'CI alpha', category: 'general', level: 'advanced', inputType: 'number', defaultValue: 0.05,
    description: 'Alpha for constructing threshold confidence interval.', min: 0.001, max: 0.5, step: 0.01,
  },
  {
    key: 'threshold_ci_frac_bootstrap', label: 'Bootstrap fraction', category: 'general', level: 'advanced', inputType: 'number', defaultValue: 1.0,
    description: '1.0 = Efron method (with replacement); < 1.0 = Politis & Romano method (without replacement).', min: 0.01, max: 1.0, step: 0.1,
  },
  {
    key: 'user_feature_penalties_weight', label: 'User penalty weight', category: 'general', level: 'advanced', inputType: 'number', defaultValue: 1.0,
    description: 'Weight applied to user-defined feature penalties from feature_annotations file.', min: 0, step: 0.1,
  },
  {
    key: 'n_model_to_display', label: 'Models to display', category: 'general', level: 'advanced', inputType: 'number', defaultValue: 30,
    description: 'Number of models shown in the last generation. 0 = show all models.', min: 0, step: 5,
  },
  {
    key: 'display_colorful', label: 'Colorful output', category: 'general', level: 'advanced', inputType: 'checkbox', defaultValue: true,
    description: 'Enable ANSI color codes in the console output for easier reading.',
  },

  // ===================== GA (17) =====================
  {
    key: 'population_size', label: 'Population size', category: 'ga', level: 'basic', inputType: 'number', defaultValue: 5000,
    description: 'Target number of models per generation. Actual count may be lower due to clone removal.', min: 10, step: 100,
  },
  {
    key: 'max_epochs', label: 'Max epochs', category: 'ga', level: 'basic', inputType: 'number', defaultValue: 200,
    description: 'Maximum number of generations before the algorithm stops.', min: 1, step: 10,
  },
  {
    key: 'min_epochs', label: 'Min epochs', category: 'ga', level: 'basic', inputType: 'number', defaultValue: 10,
    description: 'Minimum number of generations before early stopping is allowed.', min: 1, step: 1,
  },
  {
    key: 'max_age_best_model', label: 'Max age best model', category: 'ga', level: 'basic', inputType: 'number', defaultValue: 10,
    description: 'Early stop (after min_epochs) if the best model reaches this age without improvement.', min: 1, step: 5,
  },
  {
    key: 'k_min', label: 'k min', category: 'ga', level: 'basic', inputType: 'number', defaultValue: 1,
    description: 'Minimum number of variables (features) in initial population models.', min: 1, step: 1,
  },
  {
    key: 'k_max', label: 'k max', category: 'ga', level: 'basic', inputType: 'number', defaultValue: 200,
    description: 'Maximum number of variables in initial population. 0 = no maximum.', min: 0, step: 10,
  },
  // GA advanced
  {
    key: 'select_elite_pct', label: 'Elite %', category: 'ga', level: 'advanced', inputType: 'number', defaultValue: 2,
    description: 'Percentage of best models from previous generation retained. Lower = more elitist.', min: 0, max: 100, step: 1, unit: '%',
  },
  {
    key: 'select_niche_pct', label: 'Niche %', category: 'ga', level: 'advanced', inputType: 'number', defaultValue: 0,
    description: 'Percentage of best models retained per language/data type to maintain diversity.', min: 0, max: 100, step: 1, unit: '%',
  },
  {
    key: 'select_random_pct', label: 'Random %', category: 'ga', level: 'advanced', inputType: 'number', defaultValue: 2,
    description: 'Percentage of opportunistic models retained from previous generation.', min: 0, max: 100, step: 1, unit: '%',
  },
  {
    key: 'mutated_children_pct', label: 'Mutated children %', category: 'ga', level: 'advanced', inputType: 'number', defaultValue: 80,
    description: 'Percentage of children subjected to mutation.', min: 0, max: 100, step: 5, unit: '%',
  },
  {
    key: 'mutated_features_pct', label: 'Mutated features %', category: 'ga', level: 'advanced', inputType: 'number', defaultValue: 20,
    description: 'Percentage of mutation per gene (potential variable). Most mutations are nonsensical.', min: 0, max: 100, step: 5, unit: '%',
  },
  {
    key: 'mutation_non_null_chance_pct', label: 'Non-null mutation %', category: 'ga', level: 'advanced', inputType: 'number', defaultValue: 20,
    description: 'Likelihood that a mutation adds a new variable rather than just removing one.', min: 0, max: 100, step: 5, unit: '%',
  },
  {
    key: 'forced_diversity_pct', label: 'Forced diversity %', category: 'ga', level: 'advanced', inputType: 'number', defaultValue: 0,
    description: 'If > 0%, population is filtered every N epochs to enforce diversity.', min: 0, max: 100, step: 5, unit: '%',
  },
  {
    key: 'forced_diversity_epochs', label: 'Diversity epoch gap', category: 'ga', level: 'advanced', inputType: 'number', defaultValue: 10,
    description: 'Epochs between two diversity filters (when forced_diversity_pct > 0).', min: 1, step: 5, unit: 'epochs',
  },
  {
    key: 'random_sampling_pct', label: 'Random sampling %', category: 'ga', level: 'advanced', inputType: 'number', defaultValue: 0,
    description: 'If > 0%, each generation is fitted on only this percentage of random samples.', min: 0, max: 100, step: 5, unit: '%',
  },
  {
    key: 'random_sampling_epochs', label: 'Sampling epoch gap', category: 'ga', level: 'advanced', inputType: 'number', defaultValue: 1,
    description: 'Epochs during which the same randomized dataset is kept.', min: 1, step: 1, unit: 'epochs',
  },
  {
    key: 'n_epochs_before_global', label: 'Epochs before global', category: 'ga', level: 'advanced', inputType: 'number', defaultValue: 0,
    description: 'Epochs of per-language competition before merging into a global population.', min: 0, step: 5, unit: 'epochs',
  },

  // ===================== BEAM (5) =====================
  {
    key: 'method', label: 'Method', category: 'beam', level: 'basic', inputType: 'select', defaultValue: 'LimitedExhaustive',
    description: 'LimitedExhaustive: all k-combinations. ParallelForward: extend each model by one feature.',
    options: [{ value: 'LimitedExhaustive', label: 'Limited Exhaustive' }, { value: 'ParallelForward', label: 'Parallel Forward' }],
  },
  {
    key: 'k_start', label: 'k start', category: 'beam', level: 'basic', inputType: 'number', defaultValue: 1,
    description: 'Number of variables in the initial population for beam search.', min: 1, step: 1,
  },
  {
    key: 'k_stop', label: 'k stop', category: 'beam', level: 'basic', inputType: 'number', defaultValue: 100,
    description: 'Maximum number of variables in a single model.', min: 1, step: 10,
  },
  {
    key: 'best_models_criterion', label: 'Best models criterion', category: 'beam', level: 'basic', inputType: 'number', defaultValue: 10,
    description: 'If <= 1: alpha for FBM CI (smaller = larger range). If > 1: top X% of best models to keep.', min: 0, step: 1,
  },
  {
    key: 'max_nb_of_models', label: 'Max models', category: 'beam', level: 'basic', inputType: 'number', defaultValue: 10000,
    description: 'Limits features to keep at each epoch based on model count possibilities.', min: 100, step: 1000,
  },

  // ===================== MCMC (4) =====================
  {
    key: 'n_iter', label: 'Iterations', category: 'mcmc', level: 'basic', inputType: 'number', defaultValue: 10000,
    description: 'Total number of MCMC iterations.', min: 100, step: 1000,
  },
  {
    key: 'n_burn', label: 'Burn-in', category: 'mcmc', level: 'basic', inputType: 'number', defaultValue: 5000,
    description: 'Number of initial MCMC iterations to discard (typically the first half).', min: 0, step: 500,
  },
  {
    key: 'lambda', label: 'Lambda', category: 'mcmc', level: 'basic', inputType: 'number', defaultValue: 0.001,
    description: 'Bayesian prior parameter for coefficients a, b, c.', min: 0, step: 0.001,
  },
  {
    key: 'nmin', label: 'nmin', category: 'mcmc', level: 'basic', inputType: 'number', defaultValue: 10,
    description: 'Minimum features in a model after feature elimination. 0 = keep all features (disable SBS).', min: 0, step: 1,
  },

  // ===================== CV (7) =====================
  {
    key: 'outer_folds', label: 'Outer folds', category: 'cv', level: 'basic', inputType: 'number', defaultValue: 5,
    description: 'Number of outer cross-validation folds. Algorithm runs on each k-1 fold set, then merges FBMs.', min: 2, max: 20, step: 1,
  },
  {
    key: 'inner_folds', label: 'Inner folds', category: 'cv', level: 'basic', inputType: 'number', defaultValue: 5,
    description: 'Number of folds used to penalize overfitting (when overfit_penalty > 0).', min: 2, max: 20, step: 1,
  },
  {
    key: 'overfit_penalty', label: 'Overfit penalty', category: 'cv', level: 'basic', inputType: 'number', defaultValue: 0,
    description: 'Penalty: fit -= mean(fit on k-1 - |delta with last fold|) * penalty. 0 = disabled.', min: 0, max: 1, step: 0.01,
  },
  {
    key: 'resampling_inner_folds_epochs', label: 'Resample inner folds', category: 'cv', level: 'advanced', inputType: 'number', defaultValue: 0,
    description: 'Resplit inner folds every N epochs to avoid learning about fold composition. 0 = never.', min: 0, step: 5, unit: 'epochs',
  },
  {
    key: 'fit_on_valid', label: 'Fit on validation', category: 'cv', level: 'advanced', inputType: 'checkbox', defaultValue: true,
    description: 'FBM based on validation fold fit (favoring generalization). Requires external test data.',
  },
  {
    key: 'cv_best_models_ci_alpha', label: 'FBM CI alpha', category: 'cv', level: 'advanced', inputType: 'number', defaultValue: 0.05,
    description: 'Alpha for Family of Best Models CI on best validation fit. Smaller = larger range.', min: 0.001, max: 0.5, step: 0.01,
  },
  {
    key: 'stratify_by', label: 'Stratify by', category: 'cv', level: 'advanced', inputType: 'text', defaultValue: '',
    description: 'Stratify folds by classes AND this annotation column (from sample annotations file).',
  },

  // ===================== IMPORTANCE (4) =====================
  {
    key: 'compute_importance', label: 'Compute importance', category: 'importance', level: 'basic', inputType: 'checkbox', defaultValue: false,
    description: 'Compute feature importance via Mean Decrease Accuracy (MDA).',
  },
  {
    key: 'n_permutations_mda', label: 'MDA permutations', category: 'importance', level: 'basic', inputType: 'number', defaultValue: 100,
    description: 'Number of permutations per feature for MDA importance calculation.', min: 10, step: 50,
  },
  {
    key: 'scaled_importance', label: 'Scaled importance', category: 'importance', level: 'basic', inputType: 'checkbox', defaultValue: true,
    description: 'Scale importance values by feature prevalence within folds.',
  },
  {
    key: 'importance_aggregation', label: 'Aggregation', category: 'importance', level: 'basic', inputType: 'select', defaultValue: 'mean',
    description: 'Method to aggregate importance scores across folds.',
    options: [{ value: 'mean', label: 'Mean' }, { value: 'median', label: 'Median' }],
  },

  // ===================== VOTING (9) =====================
  {
    key: 'vote', label: 'Enable voting', category: 'voting', level: 'basic', inputType: 'checkbox', defaultValue: false,
    description: 'Activate voting ensemble where multiple models vote on sample classification.',
  },
  {
    key: 'fbm_ci_alpha', label: 'FBM CI alpha', category: 'voting', level: 'basic', inputType: 'number', defaultValue: 0.05,
    description: 'Alpha for Family of Best Models confidence interval. Smaller = larger best_model range.', min: 0.001, max: 0.5, step: 0.01,
  },
  {
    key: 'prune_before_voting', label: 'Prune before voting', category: 'voting', level: 'basic', inputType: 'checkbox', defaultValue: false,
    description: 'Prune models based on feature importances (remove models with MDA < 0).',
  },
  {
    key: 'min_perf', label: 'Min performance', category: 'voting', level: 'advanced', inputType: 'number', defaultValue: 0.5,
    description: 'Required sensitivity AND specificity for a judge model. >= 0.5 avoids single-choice bias.', min: 0, max: 1, step: 0.05,
  },
  {
    key: 'min_diversity', label: 'Min diversity', category: 'voting', level: 'advanced', inputType: 'number', defaultValue: 5,
    description: 'Required diversity (feature difference count) between judge models.', min: 0, step: 1,
  },
  {
    key: 'method', label: 'Voting method', category: 'voting', level: 'advanced', inputType: 'select', defaultValue: 'Majority',
    description: 'Majority: class 1 if votes > threshold. Consensus: no classification if threshold not reached.',
    options: [{ value: 'Majority', label: 'Majority' }, { value: 'Consensus', label: 'Consensus' }],
  },
  {
    key: 'method_threshold', label: 'Voting threshold', category: 'voting', level: 'advanced', inputType: 'number', defaultValue: 0.5,
    description: 'Typically 0.5 for Majority, 1 for Consensus. If 0, optimize via Youden maximum.', min: 0, max: 1, step: 0.05,
  },
  {
    key: 'threshold_windows_pct', label: 'Threshold window %', category: 'voting', level: 'advanced', inputType: 'number', defaultValue: 5,
    description: 'Samples with votes within threshold +/- this percentage are not classified.', min: 0, max: 50, step: 1, unit: '%',
  },
  {
    key: 'complete_display', label: 'Complete display', category: 'voting', level: 'advanced', inputType: 'checkbox', defaultValue: false,
    description: 'Display full voting results including all individual judge contributions.',
  },

  // ===================== GPU (4) =====================
  {
    key: 'fallback_to_cpu', label: 'Fallback to CPU', category: 'gpu', level: 'basic', inputType: 'checkbox', defaultValue: true,
    description: 'Execute on CPU (integrated graphics) if no discrete GPU available. Recommended.',
  },
  {
    key: 'memory_policy', label: 'Memory policy', category: 'gpu', level: 'basic', inputType: 'select', defaultValue: 'Strict',
    description: 'Strict: panic on limit exceeded. Adaptive: adjust if unavailable. Performance: use all GPU memory.',
    options: [{ value: 'Strict', label: 'Strict' }, { value: 'Adaptive', label: 'Adaptive' }, { value: 'Performance', label: 'Performance' }],
  },
  {
    key: 'max_total_memory_mb', label: 'Max GPU memory', category: 'gpu', level: 'basic', inputType: 'number', defaultValue: 256,
    description: 'Maximum total GPU memory in MB for all buffers.', min: 32, step: 64, unit: 'MB',
  },
  {
    key: 'max_buffer_size_mb', label: 'Max buffer size', category: 'gpu', level: 'basic', inputType: 'number', defaultValue: 128,
    description: 'Maximum GPU memory in MB for a single buffer.', min: 16, step: 32, unit: 'MB',
  },
]
