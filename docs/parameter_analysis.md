# Parameter Analysis: gpredomics vs PredomicsApp Web

This document compares all parameters from the gpredomics engine (`param.yaml` / `param.rs`) with what is currently implemented in the PredomicsApp web frontend and backend.

## Summary

| Section | gpredomics params | Frontend (parameterDefs.js) | Backend (schemas.py) | Engine (param.yaml writer) |
|---------|------------------:|----------------------------:|---------------------:|---------------------------:|
| General | 20 | 18 | 18 | 18 |
| Data | 14 | 0 (managed by DataTab) | 7 | 7 |
| GA | 17 | 17 | 17 | 17 |
| Beam | 5 | 5 | 5 | 5 |
| MCMC | 4 | 4 | 4 | 4 |
| CV | 7 | 7 | 7 | 7 |
| Importance | 4 | 4 | 4 | 4 |
| Voting | 9 | 9 | 9 | 9 |
| GPU | 4 | 4 | 4 | 4 |
| **Total** | **84** | **68** | **75** | **75** |

---

## Detailed Parameter Mapping

### General (20 in gpredomics, 18 in web app)

| Parameter | gpredomics default | Frontend | Backend | Engine | Notes |
|-----------|-------------------|:--------:|:-------:|:------:|-------|
| `seed` | 42 | Y | Y | Y | |
| `algo` | ga | Y | Y | Y | |
| `cv` | false | Y | Y | Y | |
| `thread_number` | 8 | Y | Y | Y | Default changed to 4 in web |
| `gpu` | false | Y | Y | Y | |
| `language` | bin,ratio,pow2,ter | Y | Y | Y | Default: bin,ter,ratio |
| `data_type` | raw,prev,log | Y | Y | Y | Default: raw,prev |
| `epsilon` | 1e-5 | Y | Y | Y | |
| `fit` | auc | Y | Y | Y | |
| `k_penalty` | 0.0001 | Y | Y | Y | |
| `fr_penalty` | 0.0 | Y | Y | Y | |
| `bias_penalty` | 0.0 | Y | Y | Y | |
| `threshold_ci_n_bootstrap` | 0 | Y | Y | Y | |
| `threshold_ci_penalty` | 0.5 | Y | Y | Y | |
| `threshold_ci_alpha` | 0.05 | Y | Y | Y | |
| `threshold_ci_frac_bootstrap` | 1.0 | Y | Y | Y | |
| `user_feature_penalties_weight` | 1.0 | Y | Y | Y | |
| `n_model_to_display` | 30 | Y | Y | Y | |
| **`log_level`** | info | **N** | **N** | Y (hardcoded) | Server-side only; not user-facing |
| **`display_colorful`** | true | **N** | **N** | Y (hardcoded) | Terminal display; not relevant for web |
| `keep_trace` | true | — | — | Y (hardcoded) | Always true in web (needed for results) |
| `log_base` | (commented) | — | — | — | Optional log file path; not web-relevant |
| `save_exp` | (commented) | — | — | — | Optional experiment save path |

### Data (14 in gpredomics, 7 in web app)

Data parameters are **not in the Parameters tab** — they are managed by the **Data tab** (DataTab.vue) and the file upload system.

| Parameter | gpredomics default | DataTab UI | Backend | Engine | Notes |
|-----------|-------------------|:----------:|:-------:|:------:|-------|
| `X` | (file path) | Y (upload) | — | Y (from file_id) | Resolved from uploaded file |
| `y` | (file path) | Y (upload) | — | Y (from file_id) | Resolved from uploaded file |
| `Xtest` | (file path) | Y (upload) | — | Y (from file_id) | Optional |
| `ytest` | (file path) | Y (upload) | — | Y (from file_id) | Optional |
| `holdout_ratio` | 0.20 | Y | Y | Y | |
| `features_in_rows` | true | Y | Y | Y | |
| `inverse_classes` | false | — | Y | Y | In backend but not yet in DataTab UI |
| `feature_minimal_prevalence_pct` | 10 | Y | Y | Y | |
| `feature_selection_method` | wilcoxon | Y | Y | Y | |
| `feature_maximal_adj_pvalue` | 1 | Y | Y | Y | Web default: 0.05 |
| `feature_minimal_feature_value` | 1e-4 | Y | Y | Y | Web default: 0.0 |
| **`feature_annotations`** | (empty) | **N** | **N** | **N** | File upload for feature penalties; not yet implemented |
| **`sample_annotations`** | (empty) | **N** | **N** | **N** | File upload for stratification; not yet implemented |
| **`classes`** | ["healthy","cirrhosis","unknown"] | **N** | **N** | **N** | Auto-detected from y file |
| **`max_features_per_class`** | 0 | **N** | **N** | **N** | Advanced filtering; could be added |
| **`feature_minimal_log_abs_bayes_factor`** | 2 | **N** | **N** | **N** | Only for bayesian_fisher method |

### GA (17 in gpredomics, 17 in web app) — Complete

| Parameter | gpredomics default | Frontend | Backend | Engine | Notes |
|-----------|-------------------|:--------:|:-------:|:------:|-------|
| `population_size` | 5000 | Y | Y | Y | |
| `max_epochs` | 100 | Y | Y | Y | Web default: 200 |
| `min_epochs` | 1 | Y | Y | Y | Web default: 10 |
| `max_age_best_model` | 100 | Y | Y | Y | Web default: 10 |
| `k_min` (→ kmin) | 1 | Y | Y | Y | Renamed to kmin in YAML |
| `k_max` (→ kmax) | 200 | Y | Y | Y | Renamed to kmax in YAML |
| `select_elite_pct` | 2 | Y | Y | Y | |
| `select_niche_pct` | 20 | Y | Y | Y | Web default: 0 |
| `select_random_pct` | 10 | Y | Y | Y | Web default: 2 |
| `mutated_children_pct` | 80 | Y | Y | Y | |
| `mutated_features_pct` | 20 | Y | Y | Y | |
| `mutation_non_null_chance_pct` | 20 | Y | Y | Y | |
| `forced_diversity_pct` | 0 | Y | Y | Y | |
| `forced_diversity_epochs` | 10 | Y | Y | Y | |
| `random_sampling_pct` | 0 | Y | Y | Y | |
| `random_sampling_epochs` | 1 | Y | Y | Y | |
| `n_epochs_before_global` | — | Y | Y | Y | Not in param.yaml but in param.rs |

### Beam (5 in gpredomics, 5 in web app) — Complete

| Parameter | gpredomics default | Frontend | Backend | Engine | Notes |
|-----------|-------------------|:--------:|:-------:|:------:|-------|
| `method` | LimitedExhaustive | Y | Y | Y | |
| `k_start` (→ kmin) | 1 | Y | Y | Y | Renamed to kmin in YAML |
| `k_stop` (→ kmax) | 100 | Y | Y | Y | Renamed to kmax in YAML |
| `best_models_criterion` | 10 | Y | Y | Y | |
| `max_nb_of_models` | 20000 | Y | Y | Y | Web default: 10000 |

### MCMC (4 in gpredomics, 4 in web app) — Complete

| Parameter | gpredomics default | Frontend | Backend | Engine | Notes |
|-----------|-------------------|:--------:|:-------:|:------:|-------|
| `n_iter` | 10000 | Y | Y | Y | |
| `n_burn` | 5000 | Y | Y | Y | |
| `lambda` | 0.001 | Y | Y | Y | Aliased as lambda_ in Python |
| `nmin` | 10 | Y | Y | Y | |

### CV (7 in gpredomics, 7 in web app) — Complete

| Parameter | gpredomics default | Frontend | Backend | Engine | Notes |
|-----------|-------------------|:--------:|:-------:|:------:|-------|
| `outer_folds` | 5 | Y | Y | Y | |
| `inner_folds` | 5 | Y | Y | Y | |
| `overfit_penalty` | 0 | Y | Y | Y | |
| `resampling_inner_folds_epochs` | 0 | Y | Y | Y | |
| `fit_on_valid` | true | Y | Y | Y | |
| `cv_best_models_ci_alpha` | 0.05 | Y | Y | Y | |
| `stratify_by` | (empty) | Y | Y | Y | |

### Importance (4 in gpredomics, 4 in web app) — Complete

| Parameter | gpredomics default | Frontend | Backend | Engine | Notes |
|-----------|-------------------|:--------:|:-------:|:------:|-------|
| `compute_importance` | false | Y | Y | Y | |
| `n_permutations_mda` | 100 | Y | Y | Y | |
| `scaled_importance` | true | Y | Y | Y | |
| `importance_aggregation` | mean | Y | Y | Y | |

### Voting (9 in gpredomics, 9 in web app) — Complete

| Parameter | gpredomics default | Frontend | Backend | Engine | Notes |
|-----------|-------------------|:--------:|:-------:|:------:|-------|
| `vote` | false | Y | Y | Y | |
| `fbm_ci_alpha` | 0.05 | Y | Y | Y | |
| `prune_before_voting` | false | Y | Y | Y | |
| `min_perf` | 0.50 | Y | Y | Y | |
| `min_diversity` | 10 | Y | Y | Y | Web default: 5 |
| `method` | Majority | Y | Y | Y | |
| `method_threshold` | 0.5 | Y | Y | Y | |
| `threshold_windows_pct` | 5 | Y | Y | Y | |
| `complete_display` | false | Y | Y | Y | |

### GPU (4 in gpredomics, 4 in web app) — Complete

| Parameter | gpredomics default | Frontend | Backend | Engine | Notes |
|-----------|-------------------|:--------:|:-------:|:------:|-------|
| `fallback_to_cpu` | true | Y | Y | Y | |
| `memory_policy` | Strict | Y | Y | Y | |
| `max_total_memory_mb` | 256 | Y | Y | Y | |
| `max_buffer_size_mb` | 128 | Y | Y | Y | |

---

## Parameters NOT Implemented (with reasons)

| Parameter | Section | Reason |
|-----------|---------|--------|
| `log_level` | general | Server-side logging control; not useful in web GUI. Hardcoded to "info" in engine.py. |
| `display_colorful` | general | Controls ANSI terminal colors; irrelevant for web output. Hardcoded to false. |
| `keep_trace` | general | Always enabled in web (needed to retrieve generation tracking data for UI). Hardcoded to true. |
| `log_base` | general | Optional file path for log output; not applicable to web context. |
| `save_exp` | general | Optional experiment serialization path; managed by backend job system instead. |
| `feature_annotations` | data | Requires a separate TSV file upload for user-defined feature penalties. Could be added as a future feature in the Data tab. |
| `sample_annotations` | data | Requires a separate TSV file upload for stratification annotations. Could be added as a future feature in the Data tab. |
| `classes` | data | Class labels are auto-detected from the y file by the Rust engine. No need for manual specification. |
| `max_features_per_class` | data | Advanced filtering option; features are already filtered by prevalence, p-value, and the Data tab's interactive controls. Could be added if needed. |
| `feature_minimal_log_abs_bayes_factor` | data | Only relevant when `feature_selection_method = bayesian_fisher`. Could be added conditionally in the Data tab. |

---

## Default Value Differences

Some web defaults differ from gpredomics defaults for better UX:

| Parameter | gpredomics | Web | Reason |
|-----------|-----------|-----|--------|
| `thread_number` | 8 | 4 | More conservative for shared server environments |
| `language` | bin,ratio,pow2,ter | bin,ter,ratio | Simplified default set |
| `data_type` | raw,prev,log | raw,prev | Simplified default set |
| `ga.max_epochs` | 100 | 200 | More thorough search by default |
| `ga.min_epochs` | 1 | 10 | Avoid premature stopping |
| `ga.max_age_best_model` | 100 | 10 | Faster convergence detection |
| `ga.select_niche_pct` | 20 | 0 | Disabled by default for simplicity |
| `ga.select_random_pct` | 10 | 2 | More elitist default |
| `beam.max_nb_of_models` | 20000 | 10000 | Memory-conscious default |
| `voting.min_diversity` | 10 | 5 | More permissive default |
| `feature_maximal_adj_pvalue` | 1 | 0.05 | Web applies stricter filtering by default |
| `feature_minimal_feature_value` | 1e-4 | 0.0 | No minimum by default in web |
