<template>
  <div class="settings-tab">
    <form @submit.prevent="launch" class="config-form">
      <!-- Dataset assignment (auto-detected from filenames) -->
      <section class="section">
        <h3>Data</h3>
        <div class="data-assignment">
          <div class="assign-row">
            <div class="assign-slot" :class="{ ok: xTrainDs, missing: !xTrainDs }">
              <span class="assign-label">X train:</span>
              <span v-if="xTrainDs" class="assign-file">{{ xTrainDs.filename }}</span>
              <span v-else class="assign-missing">Not found &mdash; upload in Data tab</span>
            </div>
            <div class="assign-slot" :class="{ ok: yTrainDs, missing: !yTrainDs }">
              <span class="assign-label">y train:</span>
              <span v-if="yTrainDs" class="assign-file">{{ yTrainDs.filename }}</span>
              <span v-else class="assign-missing">Not found &mdash; upload in Data tab</span>
            </div>
          </div>
          <div class="assign-row">
            <div class="assign-slot optional" :class="{ ok: xTestDs }">
              <span class="assign-label">X test:</span>
              <span v-if="xTestDs" class="assign-file">{{ xTestDs.filename }}</span>
              <span v-else class="assign-none">None (will use holdout)</span>
            </div>
            <div class="assign-slot optional" :class="{ ok: yTestDs }">
              <span class="assign-label">y test:</span>
              <span v-if="yTestDs" class="assign-file">{{ yTestDs.filename }}</span>
              <span v-else class="assign-none">None (will use holdout)</span>
            </div>
          </div>
        </div>
        <div class="form-row">
          <label>
            <input type="checkbox" v-model="form.config.data.features_in_rows" />
            Features in rows
          </label>
          <label>Holdout ratio:
            <input type="number" v-model.number="form.config.data.holdout_ratio" min="0" max="1" step="0.05" />
          </label>
        </div>
      </section>

      <!-- General settings -->
      <section class="section">
        <h3>General</h3>
        <div class="form-row">
          <label>Algorithm:
            <select v-model="form.config.general.algo">
              <option value="ga">Genetic Algorithm</option>
              <option value="beam">Beam Search</option>
              <option value="mcmc">MCMC</option>
            </select>
          </label>
          <label>Fit function:
            <select v-model="form.config.general.fit">
              <option value="auc">AUC</option>
              <option value="mcc">MCC</option>
              <option value="f1_score">F1 Score</option>
              <option value="sensitivity">Sensitivity</option>
              <option value="specificity">Specificity</option>
            </select>
          </label>
        </div>
        <div class="form-row">
          <label>Language:
            <input v-model="form.config.general.language" placeholder="bin,ter,ratio" />
          </label>
          <label>Data type:
            <input v-model="form.config.general.data_type" placeholder="raw,prev" />
          </label>
        </div>
        <div class="form-row">
          <label>Seed:
            <input type="number" v-model.number="form.config.general.seed" />
          </label>
          <label>Threads:
            <input type="number" v-model.number="form.config.general.thread_number" min="1" max="32" />
          </label>
        </div>
      </section>

      <!-- GA params -->
      <section class="section" v-if="form.config.general.algo === 'ga'">
        <h3>Genetic Algorithm</h3>
        <div class="form-row">
          <label>Population size:
            <input type="number" v-model.number="form.config.ga.population_size" min="100" step="100" />
          </label>
          <label>Max epochs:
            <input type="number" v-model.number="form.config.ga.max_epochs" min="1" />
          </label>
        </div>
        <div class="form-row">
          <label>Min epochs:
            <input type="number" v-model.number="form.config.ga.min_epochs" min="1" />
          </label>
          <label>Max age best model:
            <input type="number" v-model.number="form.config.ga.max_age_best_model" min="1" />
          </label>
        </div>
        <div class="form-row">
          <label>k min:
            <input type="number" v-model.number="form.config.ga.k_min" min="1" />
          </label>
          <label>k max:
            <input type="number" v-model.number="form.config.ga.k_max" min="1" />
          </label>
        </div>
        <details class="advanced-section">
          <summary>Selection & Mutation</summary>
          <div class="form-row">
            <label>Elite %:
              <input type="number" v-model.number="form.config.ga.select_elite_pct" min="0" max="100" step="1" />
            </label>
            <label>Niche %:
              <input type="number" v-model.number="form.config.ga.select_niche_pct" min="0" max="100" step="1" />
            </label>
          </div>
          <div class="form-row">
            <label>Random %:
              <input type="number" v-model.number="form.config.ga.select_random_pct" min="0" max="100" step="1" />
            </label>
            <label>Mutated children %:
              <input type="number" v-model.number="form.config.ga.mutated_children_pct" min="0" max="100" step="1" />
            </label>
          </div>
        </details>
      </section>

      <!-- Beam params -->
      <section class="section" v-if="form.config.general.algo === 'beam'">
        <h3>Beam Search</h3>
        <div class="form-row">
          <label>k min:
            <input type="number" v-model.number="form.config.beam.k_min" min="1" />
          </label>
          <label>k max:
            <input type="number" v-model.number="form.config.beam.k_max" min="1" />
          </label>
        </div>
        <div class="form-row">
          <label>Best models criterion:
            <input type="number" v-model.number="form.config.beam.best_models_criterion" min="1" step="1" />
          </label>
          <label>Max number of models:
            <input type="number" v-model.number="form.config.beam.max_nb_of_models" min="100" step="100" />
          </label>
        </div>
      </section>

      <!-- MCMC params -->
      <section class="section" v-if="form.config.general.algo === 'mcmc'">
        <h3>MCMC</h3>
        <div class="form-row">
          <label>Iterations:
            <input type="number" v-model.number="form.config.mcmc.n_iter" min="100" step="100" />
          </label>
          <label>Burn-in:
            <input type="number" v-model.number="form.config.mcmc.n_burn" min="0" step="100" />
          </label>
        </div>
        <div class="form-row">
          <label>Lambda:
            <input type="number" v-model.number="form.config.mcmc.lambda" min="0" step="0.001" />
          </label>
          <label>nmin:
            <input type="number" v-model.number="form.config.mcmc.nmin" min="1" />
          </label>
        </div>
      </section>

      <!-- Cross-validation -->
      <section class="section">
        <h3>Cross-Validation</h3>
        <div class="form-row">
          <label>
            <input type="checkbox" v-model="form.config.general.cv" />
            Enable cross-validation
          </label>
        </div>
        <div class="form-row" v-if="form.config.general.cv">
          <label>Outer folds:
            <input type="number" v-model.number="form.config.cv.outer_folds" min="2" max="20" />
          </label>
          <label>Inner folds:
            <input type="number" v-model.number="form.config.cv.inner_folds" min="2" max="20" />
          </label>
          <label>Overfit penalty:
            <input type="number" v-model.number="form.config.cv.overfit_penalty" min="0" max="1" step="0.01" />
          </label>
        </div>
      </section>

      <!-- Advanced settings -->
      <details class="section advanced-section">
        <summary><h3 style="display:inline">Advanced</h3></summary>
        <div class="form-row">
          <label>k penalty:
            <input type="number" v-model.number="form.config.general.k_penalty" min="0" step="0.0001" />
          </label>
          <label>
            <input type="checkbox" v-model="form.config.general.gpu" />
            GPU acceleration
          </label>
        </div>
        <div class="form-row">
          <label>Feature selection:
            <select v-model="form.config.data.feature_selection_method">
              <option value="wilcoxon">Wilcoxon</option>
              <option value="ttest">t-test</option>
              <option value="none">None</option>
            </select>
          </label>
          <label>Min prevalence %:
            <input type="number" v-model.number="form.config.data.feature_minimal_prevalence_pct" min="0" max="100" />
          </label>
        </div>
      </details>

      <div class="launch-bar">
        <button type="submit" class="btn btn-primary" :disabled="launching || !canLaunch">
          {{ launching ? 'Launching...' : 'Launch Analysis' }}
        </button>
        <span v-if="!canLaunch" class="launch-hint">Upload X and y training datasets first</span>
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore } from '../stores/project'
import axios from 'axios'

const route = useRoute()
const store = useProjectStore()
const launching = ref(false)

const datasets = computed(() => store.current?.datasets || [])

// Auto-detect dataset roles by filename patterns (same logic as DataTab)
const xTrainDs = computed(() =>
  datasets.value.find(d => /^x/i.test(d.filename) && /train/i.test(d.filename))
  || datasets.value.find(d => /^x\b/i.test(d.filename) && !/test/i.test(d.filename))
)
const yTrainDs = computed(() =>
  datasets.value.find(d => /^y/i.test(d.filename) && /train/i.test(d.filename))
  || datasets.value.find(d => /^y\b/i.test(d.filename) && !/test/i.test(d.filename))
)
const xTestDs = computed(() =>
  datasets.value.find(d => /^x/i.test(d.filename) && /test/i.test(d.filename))
)
const yTestDs = computed(() =>
  datasets.value.find(d => /^y/i.test(d.filename) && /test/i.test(d.filename))
)

const canLaunch = computed(() => xTrainDs.value && yTrainDs.value)

const form = reactive({
  config: {
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
    },
    cv: { outer_folds: 5, inner_folds: 5, overfit_penalty: 0 },
  },
})

async function launch() {
  if (!canLaunch.value) return
  launching.value = true
  try {
    const params = {
      x_dataset_id: xTrainDs.value.id,
      y_dataset_id: yTrainDs.value.id,
    }
    if (xTestDs.value) params.xtest_dataset_id = xTestDs.value.id
    if (yTestDs.value) params.ytest_dataset_id = yTestDs.value.id

    const { data } = await axios.post(
      `/api/analysis/${route.params.id}/run`,
      form.config,
      { params }
    )
    // Open console panel instead of navigating away
    store.startJob(data.job_id)
  } catch (e) {
    console.error('Launch failed:', e)
    alert('Failed to launch analysis: ' + (e.response?.data?.detail || e.message))
  } finally {
    launching.value = false
  }
}
</script>

<style scoped>
.config-form {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.section {
  background: white;
  padding: 1.5rem;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.section h3 {
  margin-bottom: 1rem;
  color: #1a1a2e;
}

.data-assignment {
  margin-bottom: 1rem;
}

.assign-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-bottom: 0.5rem;
}

.assign-slot {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  font-size: 0.85rem;
  background: #f5f7fa;
}

.assign-slot.ok {
  background: #e8f5e9;
}

.assign-slot.missing {
  background: #fff3e0;
}

.assign-label {
  font-weight: 600;
  color: #546e7a;
  min-width: 55px;
}

.assign-file {
  color: #2e7d32;
  font-weight: 500;
}

.assign-missing {
  color: #e65100;
  font-size: 0.8rem;
}

.assign-none {
  color: #90a4ae;
  font-size: 0.8rem;
  font-style: italic;
}

.form-row {
  display: flex;
  gap: 1.5rem;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
}

.form-row label {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.85rem;
  color: #546e7a;
  min-width: 180px;
}

input, select {
  padding: 0.4rem 0.6rem;
  border: 1px solid #cfd8dc;
  border-radius: 4px;
  font-size: 0.9rem;
}

input[type="checkbox"] {
  width: auto;
  align-self: flex-start;
  margin-top: 0.25rem;
}

.advanced-section {
  margin-top: 0.5rem;
}

.advanced-section summary {
  cursor: pointer;
  color: #546e7a;
  font-size: 0.85rem;
  margin-bottom: 0.75rem;
}

.launch-bar {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.btn {
  padding: 0.75rem 2rem;
  border: none;
  border-radius: 6px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
}

.btn-primary {
  background: #1a1a2e;
  color: white;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.launch-hint {
  color: #e65100;
  font-size: 0.85rem;
}
</style>
