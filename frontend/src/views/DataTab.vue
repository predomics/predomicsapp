<template>
  <div class="data-tab">
    <!-- Role-based dataset assignment -->
    <section class="section">
      <h3>Datasets</h3>
      <div class="role-grid">
        <!-- X train -->
        <div class="role-slot" :class="{ assigned: xTrain }">
          <div class="role-header">
            <strong>X train</strong>
            <span class="role-desc">Feature matrix (training)</span>
          </div>
          <div v-if="xTrain" class="role-assigned">
            <span class="check">&#10003;</span>
            <span class="filename">{{ xTrain.filename }}</span>
          </div>
          <label v-else class="upload-btn">
            <span>Upload file</span>
            <input type="file" accept=".tsv,.csv,.txt" @change="e => uploadFile(e, 'xtrain')" />
          </label>
        </div>

        <!-- y train -->
        <div class="role-slot" :class="{ assigned: yTrain }">
          <div class="role-header">
            <strong>y train</strong>
            <span class="role-desc">Labels (training)</span>
          </div>
          <div v-if="yTrain" class="role-assigned">
            <span class="check">&#10003;</span>
            <span class="filename">{{ yTrain.filename }}</span>
          </div>
          <label v-else class="upload-btn">
            <span>Upload file</span>
            <input type="file" accept=".tsv,.csv,.txt" @change="e => uploadFile(e, 'ytrain')" />
          </label>
        </div>

        <!-- X test -->
        <div class="role-slot optional" :class="{ assigned: xTest }">
          <div class="role-header">
            <strong>X test</strong>
            <span class="role-desc">Feature matrix (test, optional)</span>
          </div>
          <div v-if="xTest" class="role-assigned">
            <span class="check">&#10003;</span>
            <span class="filename">{{ xTest.filename }}</span>
          </div>
          <label v-else class="upload-btn">
            <span>Upload file</span>
            <input type="file" accept=".tsv,.csv,.txt" @change="e => uploadFile(e, 'xtest')" />
          </label>
        </div>

        <!-- y test -->
        <div class="role-slot optional" :class="{ assigned: yTest }">
          <div class="role-header">
            <strong>y test</strong>
            <span class="role-desc">Labels (test, optional)</span>
          </div>
          <div v-if="yTest" class="role-assigned">
            <span class="check">&#10003;</span>
            <span class="filename">{{ yTest.filename }}</span>
          </div>
          <label v-else class="upload-btn">
            <span>Upload file</span>
            <input type="file" accept=".tsv,.csv,.txt" @change="e => uploadFile(e, 'ytest')" />
          </label>
        </div>
      </div>

      <!-- Unassigned datasets -->
      <div v-if="unassigned.length > 0" class="unassigned-section">
        <h4>Other datasets ({{ unassigned.length }})</h4>
        <div v-for="d in unassigned" :key="d.id" class="dataset-item">
          <span class="filename">{{ d.filename }}</span>
        </div>
      </div>
    </section>

    <!-- Dataset overview -->
    <section class="section" v-if="xTrain || yTrain">
      <h3>Dataset Overview</h3>
      <div class="stat-cards">
        <div class="stat-card">
          <div class="stat-value">{{ datasets.length }}</div>
          <div class="stat-label">Datasets</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ xTrain ? '&#10003;' : '&#10007;' }}</div>
          <div class="stat-label">Train Data</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ xTest ? '&#10003;' : '&#10007;' }}</div>
          <div class="stat-label">Test Data</div>
        </div>
        <div class="stat-card" v-if="xTest && !yTest || !xTest && yTest">
          <div class="stat-value warn">!</div>
          <div class="stat-label">Test incomplete</div>
        </div>
      </div>
      <p class="info-text">
        Data exploration, statistics, and filtering will be available here in a future update.
      </p>
    </section>

    <!-- Empty state -->
    <div v-if="datasets.length === 0" class="empty-state">
      <p>No datasets loaded. Upload files above or load a demo dataset from the Projects page.</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore } from '../stores/project'
import axios from 'axios'

const route = useRoute()
const store = useProjectStore()

const datasets = computed(() => store.current?.datasets || [])

// Auto-detect dataset roles by filename patterns
const xTrain = computed(() =>
  datasets.value.find(d => /^x/i.test(d.filename) && /train/i.test(d.filename))
  || datasets.value.find(d => /^x\b/i.test(d.filename) && !/test/i.test(d.filename))
)
const yTrain = computed(() =>
  datasets.value.find(d => /^y/i.test(d.filename) && /train/i.test(d.filename))
  || datasets.value.find(d => /^y\b/i.test(d.filename) && !/test/i.test(d.filename))
)
const xTest = computed(() =>
  datasets.value.find(d => /^x/i.test(d.filename) && /test/i.test(d.filename))
)
const yTest = computed(() =>
  datasets.value.find(d => /^y/i.test(d.filename) && /test/i.test(d.filename))
)

const assignedIds = computed(() => {
  const ids = new Set()
  if (xTrain.value) ids.add(xTrain.value.id)
  if (yTrain.value) ids.add(yTrain.value.id)
  if (xTest.value) ids.add(xTest.value.id)
  if (yTest.value) ids.add(yTest.value.id)
  return ids
})

const unassigned = computed(() =>
  datasets.value.filter(d => !assignedIds.value.has(d.id))
)

async function uploadFile(event, _role) {
  const file = event.target.files[0]
  if (!file) return

  const formData = new FormData()
  formData.append('file', file)

  try {
    await axios.post(
      `/api/projects/${route.params.id}/datasets`,
      formData,
    )
    await store.fetchOne(route.params.id)
  } catch (e) {
    console.error('Upload failed:', e)
    alert('Upload failed: ' + (e.response?.data?.detail || e.message))
  }
}
</script>

<style scoped>
.section {
  background: white;
  padding: 1.5rem;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  margin-bottom: 1.5rem;
}

.section h3 {
  margin-bottom: 1rem;
  color: #1a1a2e;
}

.section h4 {
  margin: 1rem 0 0.5rem;
  color: #546e7a;
  font-size: 0.85rem;
}

.role-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.role-slot {
  border: 2px dashed #cfd8dc;
  border-radius: 8px;
  padding: 1rem;
  transition: all 0.2s;
}

.role-slot.assigned {
  border-color: #4caf50;
  border-style: solid;
  background: #f1f8e9;
}

.role-slot.optional:not(.assigned) {
  border-color: #e0e0e0;
}

.role-header {
  margin-bottom: 0.5rem;
}

.role-header strong {
  font-size: 0.95rem;
  color: #1a1a2e;
}

.role-desc {
  display: block;
  font-size: 0.75rem;
  color: #90a4ae;
  margin-top: 0.1rem;
}

.role-assigned {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
}

.check {
  color: #4caf50;
  font-weight: bold;
  font-size: 1.1rem;
}

.filename {
  font-weight: 500;
  color: #37474f;
}

.upload-btn {
  display: inline-block;
  cursor: pointer;
  font-size: 0.85rem;
  color: #1a1a2e;
  border: 1px solid #cfd8dc;
  border-radius: 4px;
  padding: 0.35rem 0.75rem;
}

.upload-btn:hover {
  background: #f5f7fa;
}

.upload-btn input[type="file"] {
  display: none;
}

.unassigned-section {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid #eceff1;
}

.dataset-item {
  padding: 0.35rem 0;
  font-size: 0.85rem;
  color: #78909c;
}

.stat-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 1rem;
  margin-bottom: 1rem;
}

.stat-card {
  background: #f5f7fa;
  padding: 1rem;
  border-radius: 8px;
  text-align: center;
}

.stat-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #1a1a2e;
}

.stat-value.warn {
  color: #f57c00;
}

.stat-label {
  font-size: 0.75rem;
  color: #90a4ae;
  margin-top: 0.25rem;
}

.info-text {
  color: #90a4ae;
  font-size: 0.85rem;
  font-style: italic;
}

.empty-state {
  text-align: center;
  padding: 2rem;
  color: #90a4ae;
}
</style>
