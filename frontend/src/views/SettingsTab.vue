<template>
  <div class="run-tab">
    <form @submit.prevent="launch">
      <!-- Compact dataset assignment with upload + library picker -->
      <section class="data-section">
        <div class="section-title">Datasets</div>
        <div class="dataset-row">
          <div v-for="slot in dsSlots" :key="slot.role" class="ds-slot" :class="{ ok: slot.ds, missing: !slot.ds && slot.required, optional: !slot.required && !slot.ds }">
            <span class="ds-role">{{ slot.label }}</span>
            <span v-if="slot.ds" class="ds-file">{{ slot.ds.filename }}
              <button class="ds-clear" @click="clearSlot(slot.role)" title="Remove">&times;</button>
            </span>
            <template v-else>
              <select v-if="libraryDatasets.length > 0" class="ds-picker" @change="e => pickFromLibrary(e, slot.role)">
                <option value="">Pick from library...</option>
                <option v-for="d in libraryDatasets" :key="d.id" :value="d.id">{{ d.name }} ({{ d.files?.length || 0 }} files)</option>
              </select>
              <label :class="['ds-upload', { 'ds-optional': !slot.required }]">Upload<input type="file" accept=".tsv,.csv,.txt" @change="e => uploadFile(e, slot.role)" /></label>
            </template>
          </div>
        </div>
      </section>

      <!-- Two-column settings grid -->
      <div class="settings-grid">
        <!-- Left column -->
        <div class="settings-col">
          <section class="section">
            <div class="section-title">General</div>
            <div class="form-row">
              <label>Algorithm
                <select v-model="form.config.general.algo">
                  <option value="ga">Genetic Algorithm</option>
                  <option value="beam">Beam Search</option>
                  <option value="mcmc">MCMC</option>
                </select>
              </label>
              <label>Fit function
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
              <label>Language
                <input v-model="form.config.general.language" placeholder="bin,ter,ratio" />
              </label>
              <label>Data type
                <input v-model="form.config.general.data_type" placeholder="raw,prev" />
              </label>
            </div>
            <div class="form-row">
              <label>Seed
                <input type="number" v-model.number="form.config.general.seed" />
              </label>
              <label>Threads
                <input type="number" v-model.number="form.config.general.thread_number" min="1" max="32" />
              </label>
            </div>
          </section>

          <!-- Cross-validation -->
          <section class="section">
            <div class="section-title">
              <label class="inline-check">
                <input type="checkbox" v-model="form.config.general.cv" />
                Cross-Validation
              </label>
            </div>
            <div class="form-row" v-if="form.config.general.cv">
              <label>Outer folds
                <input type="number" v-model.number="form.config.cv.outer_folds" min="2" max="20" />
              </label>
              <label>Inner folds
                <input type="number" v-model.number="form.config.cv.inner_folds" min="2" max="20" />
              </label>
            </div>
            <div class="form-row" v-if="form.config.general.cv">
              <label>Overfit penalty
                <input type="number" v-model.number="form.config.cv.overfit_penalty" min="0" max="1" step="0.01" />
              </label>
            </div>
          </section>

          <!-- Data options -->
          <section class="section">
            <div class="section-title">Data Options</div>
            <div class="form-row">
              <label class="inline-check">
                <input type="checkbox" v-model="form.config.data.features_in_rows" />
                Features in rows
              </label>
              <label>Holdout ratio
                <input type="number" v-model.number="form.config.data.holdout_ratio" min="0" max="1" step="0.05" />
              </label>
            </div>
            <div class="form-row">
              <label>Feature selection
                <select v-model="form.config.data.feature_selection_method">
                  <option value="wilcoxon">Wilcoxon</option>
                  <option value="studentt">t-test</option>
                  <option value="bayesian_fisher">Bayesian Fisher</option>
                  <option value="none">None</option>
                </select>
              </label>
              <label>Min prevalence %
                <input type="number" v-model.number="form.config.data.feature_minimal_prevalence_pct" min="0" max="100" />
              </label>
            </div>
            <div class="form-row">
              <label>Max adj. p-value
                <input type="number" v-model.number="form.config.data.feature_maximal_adj_pvalue" min="0" max="1" step="0.01" />
              </label>
              <label>Min feature value
                <input type="number" v-model.number="form.config.data.feature_minimal_feature_value" min="0" step="0.0001" />
              </label>
            </div>
          </section>
        </div>

        <!-- Right column -->
        <div class="settings-col">
          <!-- GA params -->
          <section class="section" v-if="form.config.general.algo === 'ga'">
            <div class="section-title">Genetic Algorithm</div>
            <div class="form-row">
              <label>Population size
                <input type="number" v-model.number="form.config.ga.population_size" min="100" step="100" />
              </label>
              <label>Max epochs
                <input type="number" v-model.number="form.config.ga.max_epochs" min="1" />
              </label>
            </div>
            <div class="form-row">
              <label>Min epochs
                <input type="number" v-model.number="form.config.ga.min_epochs" min="1" />
              </label>
              <label>Max age best model
                <input type="number" v-model.number="form.config.ga.max_age_best_model" min="1" />
              </label>
            </div>
            <div class="form-row">
              <label>k min
                <input type="number" v-model.number="form.config.ga.k_min" min="1" />
              </label>
              <label>k max
                <input type="number" v-model.number="form.config.ga.k_max" min="1" />
              </label>
            </div>
            <details class="advanced-toggle">
              <summary>Selection & Mutation</summary>
              <div class="form-row">
                <label>Elite %
                  <input type="number" v-model.number="form.config.ga.select_elite_pct" min="0" max="100" step="1" />
                </label>
                <label>Niche %
                  <input type="number" v-model.number="form.config.ga.select_niche_pct" min="0" max="100" step="1" />
                </label>
              </div>
              <div class="form-row">
                <label>Random %
                  <input type="number" v-model.number="form.config.ga.select_random_pct" min="0" max="100" step="1" />
                </label>
                <label>Mutated children %
                  <input type="number" v-model.number="form.config.ga.mutated_children_pct" min="0" max="100" step="1" />
                </label>
              </div>
            </details>
          </section>

          <!-- Beam params -->
          <section class="section" v-if="form.config.general.algo === 'beam'">
            <div class="section-title">Beam Search</div>
            <div class="form-row">
              <label>k min
                <input type="number" v-model.number="form.config.beam.k_min" min="1" />
              </label>
              <label>k max
                <input type="number" v-model.number="form.config.beam.k_max" min="1" />
              </label>
            </div>
            <div class="form-row">
              <label>Best models criterion
                <input type="number" v-model.number="form.config.beam.best_models_criterion" min="1" step="1" />
              </label>
              <label>Max models
                <input type="number" v-model.number="form.config.beam.max_nb_of_models" min="100" step="100" />
              </label>
            </div>
          </section>

          <!-- MCMC params -->
          <section class="section" v-if="form.config.general.algo === 'mcmc'">
            <div class="section-title">MCMC</div>
            <div class="form-row">
              <label>Iterations
                <input type="number" v-model.number="form.config.mcmc.n_iter" min="100" step="100" />
              </label>
              <label>Burn-in
                <input type="number" v-model.number="form.config.mcmc.n_burn" min="0" step="100" />
              </label>
            </div>
            <div class="form-row">
              <label>Lambda
                <input type="number" v-model.number="form.config.mcmc.lambda" min="0" step="0.001" />
              </label>
              <label>nmin
                <input type="number" v-model.number="form.config.mcmc.nmin" min="1" />
              </label>
            </div>
          </section>

          <!-- Advanced -->
          <section class="section">
            <details class="advanced-toggle">
              <summary class="section-title clickable">Advanced</summary>
              <div class="form-row">
                <label>k penalty
                  <input type="number" v-model.number="form.config.general.k_penalty" min="0" step="0.0001" />
                </label>
                <label class="inline-check">
                  <input type="checkbox" v-model="form.config.general.gpu" />
                  GPU acceleration
                </label>
              </div>
            </details>
          </section>
        </div>
      </div>

      <!-- Launch bar -->
      <div class="launch-bar">
        <button type="submit" class="btn btn-launch" :disabled="launching || !canLaunch">
          {{ launching ? 'Launching...' : 'Launch Analysis' }}
        </button>
        <span v-if="!canLaunch" class="launch-hint">Upload X and y training datasets first</span>
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore } from '../stores/project'
import { useDatasetStore } from '../stores/dataset'
import axios from 'axios'

const route = useRoute()
const store = useProjectStore()
const dsStore = useDatasetStore()
const launching = ref(false)

const datasets = computed(() => store.current?.datasets || [])
const libraryDatasets = computed(() => dsStore.datasets)

// Flatten all files from composite datasets for slot matching
const allFiles = computed(() =>
  datasets.value.flatMap(ds => (ds.files || []).map(f => ({ ...f, datasetId: ds.id, datasetName: ds.name })))
)

function findFile(role) {
  return allFiles.value.find(f => f.role === role) || null
}

const xTrainDs = computed(() => findFile('xtrain'))
const yTrainDs = computed(() => findFile('ytrain'))
const xTestDs = computed(() => findFile('xtest'))
const yTestDs = computed(() => findFile('ytest'))

const dsSlots = computed(() => [
  { role: 'xtrain', label: 'X train', ds: xTrainDs.value, required: true },
  { role: 'ytrain', label: 'y train', ds: yTrainDs.value, required: true },
  { role: 'xtest', label: 'X test', ds: xTestDs.value, required: false },
  { role: 'ytest', label: 'y test', ds: yTestDs.value, required: false },
])

const canLaunch = computed(() => xTrainDs.value && yTrainDs.value)

onMounted(() => dsStore.fetchDatasets())

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
      feature_maximal_adj_pvalue: 0.05,
      feature_minimal_feature_value: 0,
    },
    cv: { outer_folds: 5, inner_folds: 5, overfit_penalty: 0 },
  },
})

async function uploadFile(event, role) {
  const file = event.target.files[0]
  if (!file) return
  const formData = new FormData()
  formData.append('file', file)
  try {
    await axios.post(`/api/projects/${route.params.id}/datasets`, formData)
    await store.fetchOne(route.params.id)
    await dsStore.fetchDatasets()
  } catch (e) {
    alert('Upload failed: ' + (e.response?.data?.detail || e.message))
  }
}

async function pickFromLibrary(event, role) {
  const dsId = event.target.value
  if (!dsId) return
  try {
    await dsStore.assignDataset(dsId, route.params.id)
    await store.fetchOne(route.params.id)
  } catch (e) {
    alert('Assign failed: ' + (e.response?.data?.detail || e.message))
  }
  event.target.value = ''
}

async function clearSlot(role) {
  // Find which dataset group contains this role, then unassign the whole group
  const file = allFiles.value.find(f => f.role === role)
  if (!file) return
  try {
    await dsStore.unassignDataset(file.datasetId, route.params.id)
    await store.fetchOne(route.params.id)
  } catch (e) {
    alert('Unassign failed: ' + (e.response?.data?.detail || e.message))
  }
}

async function launch() {
  if (!canLaunch.value) return
  launching.value = true
  try {
    const params = {
      x_file_id: xTrainDs.value.id,
      y_file_id: yTrainDs.value.id,
    }
    if (xTestDs.value) params.xtest_file_id = xTestDs.value.id
    if (yTestDs.value) params.ytest_file_id = yTestDs.value.id

    const { data } = await axios.post(
      `/api/analysis/${route.params.id}/run`,
      form.config,
      { params }
    )
    store.startJob(data.job_id)
  } catch (e) {
    alert('Failed to launch: ' + (e.response?.data?.detail || e.message))
  } finally {
    launching.value = false
  }
}
</script>

<style scoped>
.run-tab {
  max-width: 100%;
}

/* Dataset strip */
.data-section {
  background: var(--bg-card);
  padding: 1rem 1.25rem;
  border-radius: 8px;
  box-shadow: var(--shadow);
  margin-bottom: 1rem;
}

.section-title {
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--text-primary);
  margin-bottom: 0.75rem;
}

.dataset-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.75rem;
}

.ds-slot {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  border: 1.5px dashed var(--border);
  font-size: 0.8rem;
}

.ds-slot.ok {
  border-color: var(--success);
  border-style: solid;
  background: var(--success-bg-alt);
}

.ds-slot.missing {
  border-color: var(--warning);
  background: var(--warning-bg-alt);
}

.ds-slot.optional:not(.ok) {
  border-color: var(--border-light);
  background: var(--bg-badge);
}

.ds-role {
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.ds-file {
  color: var(--success-dark);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ds-upload {
  cursor: pointer;
  color: var(--text-primary);
  font-size: 0.75rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.2rem 0.5rem;
  text-align: center;
  transition: background 0.15s;
}

.ds-upload:hover { background: var(--bg-card-hover); }
.ds-upload.ds-optional { color: var(--text-faint); border-color: var(--border-light); }
.ds-upload input[type="file"] { display: none; }

.ds-picker {
  font-size: 0.75rem;
  padding: 0.2rem 0.3rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-input);
  color: var(--text-body);
  max-width: 100%;
}

.ds-clear {
  background: none;
  border: none;
  color: var(--text-faint);
  cursor: pointer;
  font-size: 0.9rem;
  padding: 0 0.2rem;
  line-height: 1;
  vertical-align: middle;
}

.ds-clear:hover { color: var(--danger); }

/* Two-column settings grid */
.settings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-bottom: 1rem;
}

.settings-col {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.section {
  background: var(--bg-card);
  padding: 1rem 1.25rem;
  border-radius: 8px;
  box-shadow: var(--shadow);
}

/* Form layout */
.form-row {
  display: flex;
  gap: 1rem;
  margin-bottom: 0.6rem;
  flex-wrap: wrap;
}

.form-row label {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  font-size: 0.8rem;
  color: var(--text-secondary);
  flex: 1;
  min-width: 100px;
}

input, select {
  padding: 0.35rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 0.85rem;
  background: var(--bg-input);
  color: var(--text-body);
}

input[type="checkbox"] {
  width: auto;
  align-self: flex-start;
  margin-top: 0.15rem;
}

.inline-check {
  flex-direction: row !important;
  align-items: center;
  gap: 0.4rem !important;
  font-weight: 600;
  color: var(--text-primary) !important;
}

.advanced-toggle {
  margin-top: 0.5rem;
}

.advanced-toggle summary {
  cursor: pointer;
  color: var(--text-muted);
  font-size: 0.8rem;
  margin-bottom: 0.5rem;
}

.advanced-toggle summary.clickable {
  font-weight: 600;
  color: var(--text-primary);
  font-size: 0.9rem;
}

/* Launch bar */
.launch-bar {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 0;
}

.btn-launch {
  padding: 0.65rem 2rem;
  border: none;
  border-radius: 6px;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  background: var(--accent);
  color: var(--accent-text);
  transition: opacity 0.15s;
}

.btn-launch:hover:not(:disabled) { opacity: 0.9; }
.btn-launch:disabled { opacity: 0.5; cursor: not-allowed; }

.launch-hint {
  color: var(--warning-dark);
  font-size: 0.8rem;
}

@media (max-width: 900px) {
  .settings-grid { grid-template-columns: 1fr; }
  .dataset-row { grid-template-columns: 1fr 1fr; }
}
</style>
