import { defineStore } from 'pinia'
import { reactive, computed } from 'vue'

export const useConfigStore = defineStore('config', () => {
  const form = reactive({
    general: {
      algo: 'ga',
      language: 'bin,ter,ratio',
      data_type: 'raw,prev',
      fit: 'auc',
      seed: 42,
      thread_number: 4,
      k_penalty: 0.0001,
      cv: false,
      gpu: false,
    },
    ga: {
      population_size: 5000,
      max_epochs: 100,
      min_epochs: 1,
      max_age_best_model: 100,
      k_min: 1,
      k_max: 200,
      select_elite_pct: 2,
      select_niche_pct: 20,
      select_random_pct: 10,
      mutated_children_pct: 80,
    },
    beam: { k_min: 2, k_max: 100, best_models_criterion: 10, max_nb_of_models: 20000 },
    mcmc: { n_iter: 10000, n_burn: 5000, lambda: 0.001, nmin: 10 },
    data: {
      features_in_rows: true,
      holdout_ratio: 0.20,
      feature_selection_method: 'wilcoxon',
      feature_minimal_prevalence_pct: 10,
      feature_maximal_adj_pvalue: 0.05,
      feature_minimal_feature_value: 0,
    },
    cv: { outer_folds: 5, inner_folds: 5, overfit_penalty: 0 },
  })

  const filterParams = computed(() => ({
    method: form.data.feature_selection_method,
    prevalence_pct: form.data.feature_minimal_prevalence_pct,
    max_pvalue: form.data.feature_maximal_adj_pvalue,
    min_feature_value: form.data.feature_minimal_feature_value,
  }))

  return { form, filterParams }
})
