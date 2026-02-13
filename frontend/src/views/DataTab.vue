<template>
  <div class="data-tab">
    <!-- Upload Section -->
    <section class="section">
      <h3>Datasets</h3>
      <div class="upload-grid">
        <div class="upload-card">
          <label>
            <strong>X (features)</strong>
            <span class="hint">TSV/CSV matrix</span>
            <input type="file" accept=".tsv,.csv,.txt" @change="e => uploadFile(e, true)" />
          </label>
        </div>
        <div class="upload-card">
          <label>
            <strong>y (labels)</strong>
            <span class="hint">TSV/CSV vector</span>
            <input type="file" accept=".tsv,.csv,.txt" @change="e => uploadFile(e, false)" />
          </label>
        </div>
        <div class="upload-card">
          <label>
            <strong>X test (optional)</strong>
            <span class="hint">TSV/CSV matrix</span>
            <input type="file" accept=".tsv,.csv,.txt" @change="e => uploadFile(e, true)" />
          </label>
        </div>
        <div class="upload-card">
          <label>
            <strong>y test (optional)</strong>
            <span class="hint">TSV/CSV vector</span>
            <input type="file" accept=".tsv,.csv,.txt" @change="e => uploadFile(e, false)" />
          </label>
        </div>
      </div>

      <div v-if="datasets.length > 0" class="dataset-list">
        <div v-for="d in datasets" :key="d.id" class="dataset-item">
          <span class="filename">{{ d.filename }}</span>
          <span class="meta" v-if="d.n_features">{{ d.n_features }} features &times; {{ d.n_samples }} samples</span>
          <span class="meta" v-if="d.n_classes">({{ d.n_classes }} classes)</span>
        </div>
      </div>
      <div v-else class="empty">No datasets uploaded yet. Upload files above or load a demo from the Projects page.</div>
    </section>

    <!-- Dataset summary (Phase C placeholder) -->
    <section class="section" v-if="datasets.length > 0">
      <h3>Dataset Overview</h3>
      <div class="stat-cards">
        <div class="stat-card" v-if="xDataset">
          <div class="stat-value">{{ xDataset.n_features || '—' }}</div>
          <div class="stat-label">Features</div>
        </div>
        <div class="stat-card" v-if="xDataset">
          <div class="stat-value">{{ xDataset.n_samples || '—' }}</div>
          <div class="stat-label">Samples</div>
        </div>
        <div class="stat-card" v-if="yDataset">
          <div class="stat-value">{{ yDataset.n_classes || '—' }}</div>
          <div class="stat-label">Classes</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ datasets.length }}</div>
          <div class="stat-label">Datasets</div>
        </div>
      </div>
      <p class="info-text">
        Data exploration, statistics, and filtering will be available here in a future update.
      </p>
    </section>
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
const xDataset = computed(() => datasets.value.find(d => /^X/i.test(d.filename) && /train/i.test(d.filename))
  || datasets.value.find(d => /^X/i.test(d.filename)))
const yDataset = computed(() => datasets.value.find(d => /^Y/i.test(d.filename) && /train/i.test(d.filename))
  || datasets.value.find(d => /^Y/i.test(d.filename)))

async function uploadFile(event, featuresInRows) {
  const file = event.target.files[0]
  if (!file) return

  const formData = new FormData()
  formData.append('file', file)

  try {
    await axios.post(
      `/api/projects/${route.params.id}/datasets`,
      formData,
      { params: { features_in_rows: featuresInRows } }
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

.upload-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-bottom: 1rem;
}

.upload-card {
  border: 2px dashed #cfd8dc;
  border-radius: 8px;
  padding: 1rem;
  transition: border-color 0.2s;
}

.upload-card:hover {
  border-color: #1a1a2e;
}

.upload-card label {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  cursor: pointer;
  font-size: 0.9rem;
}

.upload-card .hint {
  color: #90a4ae;
  font-size: 0.8rem;
}

.upload-card input[type="file"] {
  margin-top: 0.5rem;
  font-size: 0.8rem;
}

.dataset-list {
  margin-top: 1rem;
}

.dataset-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid #eceff1;
  font-size: 0.9rem;
}

.dataset-item .filename {
  font-weight: 500;
}

.dataset-item .meta {
  color: #78909c;
  font-size: 0.8rem;
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

.empty {
  color: #90a4ae;
  padding: 1rem 0;
}
</style>
