<template>
  <Teleport to="body">
    <div class="preview-overlay" @click.self="$emit('close')">
      <div class="preview-modal" v-dialog="() => $emit('close')" aria-labelledby="preview-modal-title">
        <div class="preview-header">
          <h3 id="preview-modal-title">{{ filename || $t('components.filePreview') }}</h3>
          <div class="preview-meta" v-if="preview">
            <span class="meta-badge">{{ $t('modals.previewRows', { n: preview.total_rows }) }}</span>
            <span class="meta-badge">{{ $t('modals.previewCols', { n: preview.total_cols }) }}</span>
            <span class="meta-badge">{{ preview.delimiter }}</span>
            <span class="meta-badge" v-if="preview.role">{{ preview.role }}</span>
            <span class="meta-badge dim">{{ formatSize(preview.file_size_bytes) }}</span>
          </div>
          <button :aria-label="$t('common.close')" class="close-btn" @click="$emit('close')">&times;</button>
        </div>

        <div v-if="loading" class="preview-loading" role="status">{{ $t('modals.previewLoading') }}</div>
        <div v-else-if="error" class="preview-error">{{ error }}</div>
        <template v-else-if="preview">
          <div class="table-wrap">
            <table class="preview-table">
              <thead>
                <tr>
                  <th class="row-num">#</th>
                  <th v-for="col in preview.columns" :key="col" :title="statTitle(col)">
                    {{ col }}
                    <span class="col-type">{{ preview.stats[col]?.type === 'numeric' ? 'num' : 'txt' }}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, idx) in preview.rows" :key="idx">
                  <td class="row-num">{{ idx + 1 }}</td>
                  <td v-for="(cell, ci) in row" :key="ci" :class="{ numeric: preview.stats[preview.columns[ci]]?.type === 'numeric' }">
                    {{ cell }}
                  </td>
                </tr>
              </tbody>
              <tfoot v-if="hasNumericStats">
                <tr class="stat-row">
                  <td class="row-num">{{ $t('components.statMin') }}</td>
                  <td v-for="col in preview.columns" :key="'min-'+col">
                    {{ preview.stats[col]?.type === 'numeric' ? preview.stats[col].min : '' }}
                  </td>
                </tr>
                <tr class="stat-row">
                  <td class="row-num">{{ $t('components.statMax') }}</td>
                  <td v-for="col in preview.columns" :key="'max-'+col">
                    {{ preview.stats[col]?.type === 'numeric' ? preview.stats[col].max : '' }}
                  </td>
                </tr>
                <tr class="stat-row">
                  <td class="row-num">{{ $t('components.statMean') }}</td>
                  <td v-for="col in preview.columns" :key="'mean-'+col">
                    {{ preview.stats[col]?.type === 'numeric' ? preview.stats[col].mean : '' }}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
          <div class="preview-footer" v-if="preview.total_rows > preview.rows.length">
            {{ $t('components.showingFirstRows', { shown: preview.rows.length, total: preview.total_rows }) }}
          </div>
        </template>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { apiError } from '../utils/apiError'
import { vDialog } from '../directives/dialog'

const props = defineProps({
  datasetId: { type: String, required: true },
  fileId: { type: String, required: true },
  filename: { type: String, default: '' },
})

defineEmits(['close'])

const preview = ref(null)
const loading = ref(true)
const error = ref('')

const hasNumericStats = computed(() => {
  if (!preview.value?.stats) return false
  return Object.values(preview.value.stats).some(s => s.type === 'numeric')
})

function statTitle(col) {
  const s = preview.value?.stats?.[col]
  if (!s || s.type !== 'numeric') return col
  return `${col}\nmin: ${s.min}  max: ${s.max}\nmean: ${s.mean}  std: ${s.std}`
}

function formatSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

onMounted(async () => {
  try {
    const { data } = await api.datasets.previewFile(props.datasetId, props.fileId,
      { params: { rows: 20 } },
    )
    preview.value = data
  } catch (e) {
    error.value = apiError(e)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.preview-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(2px);
}

.preview-modal {
  background: var(--bg-card);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.3);
  width: 90vw;
  max-width: 1100px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.preview-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border-lighter);
  flex-shrink: 0;
}

.preview-header h3 {
  margin: 0;
  font-size: 0.95rem;
  color: var(--text-primary);
}

.preview-meta {
  display: flex;
  gap: 0.4rem;
  flex: 1;
}

.meta-badge {
  padding: 0.15rem 0.4rem;
  background: var(--bg-badge);
  border-radius: 4px;
  font-size: 0.75rem;
  color: var(--text-secondary);
  font-weight: 500;
}

.meta-badge.dim { color: var(--text-muted); }

.close-btn {
  background: none;
  border: none;
  font-size: 1.4rem;
  cursor: pointer;
  color: var(--text-muted);
  padding: 0 0.25rem;
  line-height: 1;
}
.close-btn:hover { color: var(--text-primary); }

.preview-loading, .preview-error {
  padding: 3rem;
  text-align: center;
  color: var(--text-muted);
}
.preview-error { color: var(--danger); }

.table-wrap {
  overflow: auto;
  flex: 1;
}

.preview-table {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
  font-size: 0.78rem;
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
}

.preview-table th, .preview-table td {
  padding: 0.3rem 0.6rem;
  border: 1px solid var(--border-lighter);
  white-space: nowrap;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.preview-table th {
  background: var(--bg-badge);
  position: sticky;
  top: 0;
  font-weight: 600;
  color: var(--text-secondary);
  z-index: 1;
}

.col-type {
  display: block;
  font-size: 0.75rem;
  font-weight: 400;
  color: var(--text-muted);
  text-transform: uppercase;
}

.row-num {
  color: var(--text-muted);
  font-size: 0.75rem;
  text-align: center;
  background: var(--bg-badge);
  min-width: 30px;
}

td.numeric { text-align: right; }

.stat-row td {
  background: var(--bg-badge);
  color: var(--text-muted);
  font-size: 0.75rem;
  font-style: italic;
}

.preview-footer {
  padding: 0.5rem 1rem;
  border-top: 1px solid var(--border-lighter);
  font-size: 0.78rem;
  color: var(--text-muted);
  text-align: center;
  flex-shrink: 0;
}
</style>
