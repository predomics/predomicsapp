<template>
  <div class="run-analysis">
    <h2>Run Analysis</h2>

    <form @submit.prevent="launch" class="config-form">
      <!-- Dataset selection -->
      <section class="section">
        <h3>Data</h3>
        <div class="form-row">
          <label>X (features):
            <select v-model="form.x_dataset_id" required>
              <option value="" disabled>Select X dataset</option>
              <option v-for="d in datasets" :key="d.id" :value="d.id">{{ d.filename }}</option>
            </select>
          </label>
          <label>y (labels):
            <select v-model="form.y_dataset_id" required>
              <option value="" disabled>Select y dataset</option>
              <option v-for="d in datasets" :key="d.id" :value="d.id">{{ d.filename }}</option>
            </select>
          </label>
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

      <!-- General -->
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
          <label>k min:
            <input type="number" v-model.number="form.config.ga.k_min" min="1" />
          </label>
          <label>k max:
            <input type="number" v-model.number="form.config.ga.k_max" min="1" />
          </label>
        </div>
      </section>

      <button type="submit" class="btn btn-primary" :disabled="launching">
        {{ launching ? 'Launching...' : 'Launch Analysis' }}
      </button>
    </form>

    <div v-if="jobId" class="result-link">
      Analysis launched!
      <router-link :to="`/project/${$route.params.id}/results/${jobId}`">
        View Results
      </router-link>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'

const route = useRoute()
const router = useRouter()
const launching = ref(false)
const jobId = ref(null)
const datasets = ref([])

const form = reactive({
  x_dataset_id: '',
  y_dataset_id: '',
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
    data: { features_in_rows: true, holdout_ratio: 0.20, feature_selection_method: 'wilcoxon' },
    cv: { outer_folds: 5, inner_folds: 5, overfit_penalty: 0 },
  },
})

async function fetchDatasets() {
  try {
    const { data } = await axios.get(`/api/projects/${route.params.id}`)
    datasets.value = data.datasets || []
    // Auto-select X and Y by filename pattern
    const xDs = datasets.value.find(d => /^X/i.test(d.filename) && /train/i.test(d.filename))
      || datasets.value.find(d => /^X/i.test(d.filename))
    const yDs = datasets.value.find(d => /^Y/i.test(d.filename) && /train/i.test(d.filename))
      || datasets.value.find(d => /^Y/i.test(d.filename))
    if (xDs) form.x_dataset_id = xDs.id
    if (yDs) form.y_dataset_id = yDs.id
  } catch (e) {
    console.error('Failed to load datasets:', e)
  }
}

onMounted(fetchDatasets)

async function launch() {
  launching.value = true
  try {
    const { data } = await axios.post(
      `/api/analysis/${route.params.id}/run`,
      form.config,
      {
        params: {
          x_dataset_id: form.x_dataset_id,
          y_dataset_id: form.y_dataset_id,
        },
      }
    )
    jobId.value = data.job_id
    router.push(`/project/${route.params.id}/results/${data.job_id}`)
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

.btn {
  padding: 0.75rem 2rem;
  border: none;
  border-radius: 6px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  align-self: flex-start;
}

.btn-primary {
  background: #1a1a2e;
  color: white;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.result-link {
  margin-top: 1.5rem;
  padding: 1rem;
  background: #e8f5e9;
  border-radius: 6px;
  font-size: 0.95rem;
}

.result-link a {
  color: #2e7d32;
  font-weight: 600;
}
</style>
