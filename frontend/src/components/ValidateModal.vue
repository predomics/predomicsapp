<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <div class="modal-header">
        <h3>Validate on New Data</h3>
        <button class="close-btn" @click="$emit('close')">&times;</button>
      </div>

      <div class="modal-body">
        <p class="hint">Upload an independent validation cohort to score against the trained model.</p>

        <label class="file-label">
          X matrix (TSV) <span class="required">*</span>
          <input type="file" accept=".tsv,.csv,.txt" @change="onXFile" />
        </label>

        <label class="file-label">
          Y labels (TSV) <em class="optional">optional — enables AUC/accuracy</em>
          <input type="file" accept=".tsv,.csv,.txt" @change="onYFile" />
        </label>

        <label class="checkbox-label">
          <input type="checkbox" v-model="featuresInRows" />
          Features in rows (standard gpredomics format)
        </label>

        <button class="btn btn-primary" :disabled="!xFile || running" @click="runValidation">
          {{ running ? 'Validating...' : 'Run Validation' }}
        </button>

        <div v-if="error" class="msg msg-error">{{ error }}</div>

        <!-- Results -->
        <div v-if="result" class="validation-results">
          <h4>Validation Results</h4>

          <div class="match-info">
            <span class="badge badge-ok">{{ result.matched_features.length }} features matched</span>
            <span v-if="result.missing_features.length" class="badge badge-warn">{{ result.missing_features.length }} missing</span>
            <span class="badge">{{ result.n_samples }} samples</span>
          </div>

          <!-- Evaluation metrics -->
          <div v-if="result.evaluation" class="metrics-grid">
            <div class="metric-card">
              <div class="metric-value">{{ result.evaluation.auc.toFixed(4) }}</div>
              <div class="metric-label">AUC</div>
            </div>
            <div class="metric-card">
              <div class="metric-value">{{ result.evaluation.accuracy.toFixed(4) }}</div>
              <div class="metric-label">Accuracy</div>
            </div>
            <div class="metric-card">
              <div class="metric-value">{{ result.evaluation.sensitivity.toFixed(4) }}</div>
              <div class="metric-label">Sensitivity</div>
            </div>
            <div class="metric-card">
              <div class="metric-value">{{ result.evaluation.specificity.toFixed(4) }}</div>
              <div class="metric-label">Specificity</div>
            </div>
          </div>

          <!-- Confusion matrix -->
          <div v-if="result.evaluation" class="confusion-section">
            <h5>Confusion Matrix</h5>
            <table class="confusion-table">
              <thead>
                <tr><th></th><th>Pred 1</th><th>Pred 0</th></tr>
              </thead>
              <tbody>
                <tr>
                  <td class="row-label">Real 1</td>
                  <td class="tp">{{ result.evaluation.confusion_matrix.tp }}</td>
                  <td class="fn">{{ result.evaluation.confusion_matrix.fn }}</td>
                </tr>
                <tr>
                  <td class="row-label">Real 0</td>
                  <td class="fp">{{ result.evaluation.confusion_matrix.fp }}</td>
                  <td class="tn">{{ result.evaluation.confusion_matrix.tn }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Per-sample predictions table -->
          <div class="predictions-section">
            <h5>Per-Sample Predictions ({{ result.sample_names.length }})</h5>
            <div class="predictions-scroll">
              <table class="predictions-table">
                <thead>
                  <tr>
                    <th>Sample</th>
                    <th>Score</th>
                    <th>Predicted</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(name, i) in result.sample_names" :key="name">
                    <td>{{ name }}</td>
                    <td>{{ result.scores[i].toFixed(4) }}</td>
                    <td :class="result.predicted_classes[i] === 1 ? 'class-1' : 'class-0'">
                      {{ result.predicted_classes[i] }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Missing features -->
          <details v-if="result.missing_features.length > 0" class="missing-details">
            <summary>{{ result.missing_features.length }} missing features (not in uploaded data)</summary>
            <ul>
              <li v-for="f in result.missing_features" :key="f">{{ f }}</li>
            </ul>
          </details>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import axios from 'axios'

const props = defineProps({
  projectId: String,
  jobId: String,
})
const emit = defineEmits(['close'])

const xFile = ref(null)
const yFile = ref(null)
const featuresInRows = ref(true)
const running = ref(false)
const error = ref('')
const result = ref(null)

function onXFile(e) {
  xFile.value = e.target.files[0] || null
  result.value = null
  error.value = ''
}

function onYFile(e) {
  yFile.value = e.target.files[0] || null
}

async function runValidation() {
  if (!xFile.value) return
  running.value = true
  error.value = ''
  result.value = null

  const form = new FormData()
  form.append('x_file', xFile.value)
  if (yFile.value) form.append('y_file', yFile.value)
  form.append('features_in_rows', featuresInRows.value)

  try {
    const { data } = await axios.post(
      `/api/analysis/${props.projectId}/jobs/${props.jobId}/validate`,
      form,
    )
    result.value = data
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    running.value = false
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.modal {
  background: var(--bg-card, #1a1f2e);
  border: 1px solid var(--border-color, #2a2f3e);
  border-radius: 12px;
  width: 600px; max-width: 95vw;
  max-height: 90vh; overflow-y: auto;
  padding: 1.5rem;
}
.modal-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 1rem;
}
.modal-header h3 { margin: 0; font-size: 1.2rem; }
.close-btn {
  background: none; border: none; color: var(--text-secondary, #8888a0);
  font-size: 1.5rem; cursor: pointer; line-height: 1;
}
.close-btn:hover { color: var(--text-primary, #d0d0dc); }

.hint { color: var(--text-secondary, #8888a0); font-size: 0.85rem; margin-bottom: 1rem; }

.file-label {
  display: block; margin-bottom: 0.75rem; font-size: 0.9rem;
  color: var(--text-primary, #d0d0dc);
}
.file-label input[type="file"] {
  display: block; margin-top: 0.3rem;
}
.required { color: #FF3030; }
.optional { color: var(--text-secondary, #8888a0); font-size: 0.8rem; font-style: italic; }

.checkbox-label {
  display: flex; align-items: center; gap: 0.5rem;
  font-size: 0.85rem; margin-bottom: 1rem;
  color: var(--text-primary, #d0d0dc);
}

.btn { padding: 0.5rem 1.2rem; border-radius: 6px; border: none; cursor: pointer; font-size: 0.9rem; }
.btn-primary { background: var(--accent, #00BFFF); color: #fff; }
.btn-primary:hover { opacity: 0.9; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.msg { padding: 0.5rem 0.75rem; border-radius: 6px; margin-top: 0.75rem; font-size: 0.85rem; }
.msg-error { background: rgba(255, 48, 48, 0.15); color: #FF3030; border: 1px solid rgba(255, 48, 48, 0.3); }

.validation-results { margin-top: 1.25rem; }
.validation-results h4 { margin-bottom: 0.75rem; color: var(--accent, #00BFFF); }
.validation-results h5 { margin: 1rem 0 0.5rem; font-size: 0.9rem; }

.match-info { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem; }
.badge {
  display: inline-block; padding: 0.2rem 0.6rem; border-radius: 12px;
  font-size: 0.75rem; background: rgba(255,255,255,0.08);
  color: var(--text-secondary, #8888a0);
}
.badge-ok { background: rgba(0, 191, 255, 0.15); color: #00BFFF; }
.badge-warn { background: rgba(255, 165, 0, 0.15); color: orange; }

.metrics-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem;
  margin-bottom: 1rem;
}
.metric-card {
  background: var(--bg-primary, #0f1219); border: 1px solid var(--border-color, #2a2f3e);
  border-radius: 8px; padding: 0.6rem; text-align: center;
}
.metric-value { font-size: 1.2rem; font-weight: 700; color: var(--accent, #00BFFF); }
.metric-label { font-size: 0.7rem; color: var(--text-secondary, #8888a0); text-transform: uppercase; letter-spacing: 0.05em; }

.confusion-table {
  border-collapse: collapse; font-size: 0.85rem; margin-bottom: 0.5rem;
}
.confusion-table th, .confusion-table td {
  padding: 0.4rem 0.75rem; border: 1px solid var(--border-color, #2a2f3e); text-align: center;
}
.confusion-table th { background: var(--bg-primary, #0f1219); font-size: 0.75rem; color: var(--text-secondary, #8888a0); }
.row-label { font-weight: 600; text-align: left; }
.tp, .tn { color: #4ade80; }
.fp, .fn { color: #FF3030; }

.predictions-scroll { max-height: 300px; overflow-y: auto; }
.predictions-table {
  width: 100%; border-collapse: collapse; font-size: 0.8rem;
}
.predictions-table th, .predictions-table td {
  padding: 0.3rem 0.5rem; border-bottom: 1px solid var(--border-color, #2a2f3e);
}
.predictions-table th {
  position: sticky; top: 0; background: var(--bg-card, #1a1f2e);
  font-size: 0.7rem; text-transform: uppercase; color: var(--text-secondary, #8888a0);
}
.class-1 { color: #00BFFF; }
.class-0 { color: #FF3030; }

.missing-details { margin-top: 0.75rem; font-size: 0.8rem; color: var(--text-secondary, #8888a0); }
.missing-details ul { padding-left: 1.5rem; margin-top: 0.3rem; }
.missing-details li { margin-bottom: 0.15rem; }
</style>
