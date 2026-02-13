<template>
  <div class="params-tab">
    <form @submit.prevent="launch">
      <div class="settings-grid">
        <!-- Left column -->
        <div class="settings-col">
          <section class="section">
            <div class="section-title">General</div>
            <div class="form-row">
              <label>Algorithm
                <select v-model="cfg.general.algo">
                  <option value="ga">Genetic Algorithm</option>
                  <option value="beam">Beam Search</option>
                  <option value="mcmc">MCMC</option>
                </select>
              </label>
              <label>Fit function
                <select v-model="cfg.general.fit">
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
                <input v-model="cfg.general.language" placeholder="bin,ter,ratio" />
              </label>
              <label>Data type
                <input v-model="cfg.general.data_type" placeholder="raw,prev" />
              </label>
            </div>
            <div class="form-row">
              <label>Seed
                <input type="number" v-model.number="cfg.general.seed" />
              </label>
              <label>Threads
                <input type="number" v-model.number="cfg.general.thread_number" min="1" max="32" />
              </label>
            </div>
          </section>

          <!-- Cross-validation -->
          <section class="section">
            <div class="section-title">
              <label class="inline-check">
                <input type="checkbox" v-model="cfg.general.cv" />
                Cross-Validation
              </label>
            </div>
            <div class="form-row" v-if="cfg.general.cv">
              <label>Outer folds
                <input type="number" v-model.number="cfg.cv.outer_folds" min="2" max="20" />
              </label>
              <label>Inner folds
                <input type="number" v-model.number="cfg.cv.inner_folds" min="2" max="20" />
              </label>
            </div>
            <div class="form-row" v-if="cfg.general.cv">
              <label>Overfit penalty
                <input type="number" v-model.number="cfg.cv.overfit_penalty" min="0" max="1" step="0.01" />
              </label>
            </div>
          </section>

          <!-- Data filtering summary (read-only) -->
          <section class="section info-section">
            <div class="section-title">Data Filtering</div>
            <div class="info-row"><span class="info-label">Method:</span> {{ cfg.data.feature_selection_method }}</div>
            <div class="info-row"><span class="info-label">Min prevalence:</span> {{ cfg.data.feature_minimal_prevalence_pct }}%</div>
            <div class="info-row"><span class="info-label">Max p-value:</span> {{ cfg.data.feature_maximal_adj_pvalue }}</div>
            <div class="info-row"><span class="info-label">Holdout ratio:</span> {{ cfg.data.holdout_ratio }}</div>
            <router-link :to="`/project/${route.params.id}/data`" class="edit-link">Edit in Data tab</router-link>
          </section>
        </div>

        <!-- Right column -->
        <div class="settings-col">
          <!-- GA params -->
          <section class="section" v-if="cfg.general.algo === 'ga'">
            <div class="section-title">Genetic Algorithm</div>
            <div class="form-row">
              <label>Population size
                <input type="number" v-model.number="cfg.ga.population_size" min="100" step="100" />
              </label>
              <label>Max epochs
                <input type="number" v-model.number="cfg.ga.max_epochs" min="1" />
              </label>
            </div>
            <div class="form-row">
              <label>Min epochs
                <input type="number" v-model.number="cfg.ga.min_epochs" min="1" />
              </label>
              <label>Max age best model
                <input type="number" v-model.number="cfg.ga.max_age_best_model" min="1" />
              </label>
            </div>
            <div class="form-row">
              <label>k min
                <input type="number" v-model.number="cfg.ga.k_min" min="1" />
              </label>
              <label>k max
                <input type="number" v-model.number="cfg.ga.k_max" min="1" />
              </label>
            </div>
            <details class="advanced-toggle">
              <summary>Selection & Mutation</summary>
              <div class="form-row">
                <label>Elite %
                  <input type="number" v-model.number="cfg.ga.select_elite_pct" min="0" max="100" step="1" />
                </label>
                <label>Niche %
                  <input type="number" v-model.number="cfg.ga.select_niche_pct" min="0" max="100" step="1" />
                </label>
              </div>
              <div class="form-row">
                <label>Random %
                  <input type="number" v-model.number="cfg.ga.select_random_pct" min="0" max="100" step="1" />
                </label>
                <label>Mutated children %
                  <input type="number" v-model.number="cfg.ga.mutated_children_pct" min="0" max="100" step="1" />
                </label>
              </div>
            </details>
          </section>

          <!-- Beam params -->
          <section class="section" v-if="cfg.general.algo === 'beam'">
            <div class="section-title">Beam Search</div>
            <div class="form-row">
              <label>k min
                <input type="number" v-model.number="cfg.beam.k_min" min="1" />
              </label>
              <label>k max
                <input type="number" v-model.number="cfg.beam.k_max" min="1" />
              </label>
            </div>
            <div class="form-row">
              <label>Best models criterion
                <input type="number" v-model.number="cfg.beam.best_models_criterion" min="1" step="1" />
              </label>
              <label>Max models
                <input type="number" v-model.number="cfg.beam.max_nb_of_models" min="100" step="100" />
              </label>
            </div>
          </section>

          <!-- MCMC params -->
          <section class="section" v-if="cfg.general.algo === 'mcmc'">
            <div class="section-title">MCMC</div>
            <div class="form-row">
              <label>Iterations
                <input type="number" v-model.number="cfg.mcmc.n_iter" min="100" step="100" />
              </label>
              <label>Burn-in
                <input type="number" v-model.number="cfg.mcmc.n_burn" min="0" step="100" />
              </label>
            </div>
            <div class="form-row">
              <label>Lambda
                <input type="number" v-model.number="cfg.mcmc.lambda" min="0" step="0.001" />
              </label>
              <label>nmin
                <input type="number" v-model.number="cfg.mcmc.nmin" min="1" />
              </label>
            </div>
          </section>

          <!-- Advanced -->
          <section class="section">
            <details class="advanced-toggle">
              <summary class="section-title clickable">Advanced</summary>
              <div class="form-row">
                <label>k penalty
                  <input type="number" v-model.number="cfg.general.k_penalty" min="0" step="0.0001" />
                </label>
                <label class="inline-check">
                  <input type="checkbox" v-model="cfg.general.gpu" />
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
        <span v-if="!canLaunch" class="launch-hint">Upload X and y training datasets in the Data tab first</span>
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore } from '../stores/project'
import { useConfigStore } from '../stores/config'
import axios from 'axios'

const route = useRoute()
const store = useProjectStore()
const configStore = useConfigStore()
const cfg = configStore.form
const launching = ref(false)

const datasets = computed(() => store.current?.datasets || [])
const allFiles = computed(() =>
  datasets.value.flatMap(ds => (ds.files || []).map(f => ({ ...f, datasetId: ds.id })))
)
function findFile(role) { return allFiles.value.find(f => f.role === role) || null }
const xTrainDs = computed(() => findFile('xtrain'))
const yTrainDs = computed(() => findFile('ytrain'))
const xTestDs = computed(() => findFile('xtest'))
const yTestDs = computed(() => findFile('ytest'))
const canLaunch = computed(() => xTrainDs.value && yTrainDs.value)

async function launch() {
  if (!canLaunch.value) return
  launching.value = true
  try {
    const params = { x_file_id: xTrainDs.value.id, y_file_id: yTrainDs.value.id }
    if (xTestDs.value) params.xtest_file_id = xTestDs.value.id
    if (yTestDs.value) params.ytest_file_id = yTestDs.value.id

    const { data } = await axios.post(
      `/api/analysis/${route.params.id}/run`,
      cfg,
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
.params-tab { max-width: 100%; }

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

.section-title {
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--text-primary);
  margin-bottom: 0.75rem;
}

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

.advanced-toggle { margin-top: 0.5rem; }
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

.info-section { background: var(--bg-badge); }
.info-row {
  font-size: 0.8rem;
  color: var(--text-body);
  margin-bottom: 0.3rem;
}
.info-label {
  color: var(--text-muted);
  display: inline-block;
  min-width: 100px;
}
.edit-link {
  font-size: 0.8rem;
  color: var(--accent);
  text-decoration: none;
  margin-top: 0.5rem;
  display: inline-block;
}
.edit-link:hover { text-decoration: underline; }

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
.launch-hint { color: var(--warning-dark); font-size: 0.8rem; }

@media (max-width: 900px) {
  .settings-grid { grid-template-columns: 1fr; }
}
</style>
