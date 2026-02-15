<template>
  <div class="datasets">
    <h2>Dataset Library</h2>

    <!-- Search & filter bar -->
    <div class="filter-bar">
      <input v-model="searchQuery" placeholder="Search datasets..." class="search-input" @input="applyFilters" />
      <div class="tag-filter-wrap">
        <select v-model="filterTag" class="tag-filter" @change="applyFilters">
          <option value="">All tags</option>
          <option v-for="t in store.tagSuggestions" :key="t" :value="t">{{ t }}</option>
        </select>
      </div>
      <button v-if="searchQuery || filterTag" class="clear-filter" @click="clearFilters">Clear</button>
    </div>

    <!-- Create group form -->
    <div class="create-form">
      <input v-model="groupName" placeholder="Dataset group name..." class="name-input" @keyup.enter="createGroup" />
      <input v-model="groupDesc" placeholder="Description (optional)" class="desc-input" />
      <input v-model="groupTags" placeholder="Tags (comma-separated)" class="tags-input" />
      <button @click="createGroup" :disabled="!groupName.trim() || creating">
        {{ creating ? 'Creating...' : 'Create Group' }}
      </button>
    </div>

    <div v-if="store.loading" class="loading">Loading...</div>

    <div v-if="!store.loading && store.datasets.length === 0" class="empty">
      <template v-if="searchQuery || filterTag">No datasets match your filter.</template>
      <template v-else>No datasets yet. Create a group above, then upload files into it.</template>
    </div>

    <div v-if="store.datasets.length > 0" class="dataset-list">
      <div v-for="d in store.datasets" :key="d.id" class="dataset-card">
        <div class="card-header">
          <div class="card-content">
            <h3>{{ d.name }}</h3>
            <p v-if="d.description" class="desc">{{ d.description }}</p>
            <!-- Tags -->
            <div class="tag-row" v-if="d.tags?.length > 0 || editingTagsId === d.id">
              <template v-if="editingTagsId !== d.id">
                <span v-for="tag in d.tags" :key="tag" class="tag-chip" @click="filterByTag(tag)">{{ tag }}</span>
                <button class="tag-edit-btn" @click="startEditTags(d)" title="Edit tags">+</button>
              </template>
              <template v-else>
                <input
                  v-model="editTagsValue"
                  class="tag-edit-input"
                  placeholder="comma-separated tags..."
                  @keyup.enter="saveTags(d)"
                  @keyup.escape="editingTagsId = null"
                  ref="tagEditInput"
                  list="tag-suggestions"
                />
                <button class="tag-save-btn" @click="saveTags(d)">Save</button>
                <button class="tag-cancel-btn" @click="editingTagsId = null">Cancel</button>
              </template>
            </div>
            <div class="tag-row" v-else>
              <button class="tag-edit-btn add-first" @click="startEditTags(d)" title="Add tags">+ Add tags</button>
            </div>
            <div class="meta">
              <span>{{ formatDate(d.created_at) }}</span>
              <span>{{ d.files?.length || 0 }} file{{ (d.files?.length || 0) !== 1 ? 's' : '' }}</span>
              <span v-if="d.project_count > 0">{{ d.project_count }} project{{ d.project_count > 1 ? 's' : '' }}</span>
              <span v-else class="unused">Not assigned</span>
            </div>
          </div>
          <button class="delete-btn" @click="deleteDs(d)" title="Delete dataset group">&times;</button>
        </div>

        <!-- Files within group -->
        <div class="file-list" v-if="d.files?.length > 0">
          <div v-for="f in d.files" :key="f.id" class="file-row">
            <span class="file-name">{{ f.filename }}</span>
            <span v-if="f.role" class="file-role">{{ f.role }}</span>
            <button class="file-del" @click="deleteFile(d, f)" title="Remove file">&times;</button>
          </div>
        </div>

        <!-- Upload file into group -->
        <label class="upload-into">
          + Add file
          <input type="file" accept=".tsv,.csv,.txt" @change="e => addFile(e, d.id)" />
        </label>
      </div>
    </div>

    <!-- Tag suggestions datalist -->
    <datalist id="tag-suggestions">
      <option v-for="t in store.tagSuggestions" :key="t" :value="t" />
    </datalist>

    <div v-if="message" :class="['msg', msgType]">{{ message }}</div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { useDatasetStore } from '../stores/dataset'

const store = useDatasetStore()
const groupName = ref('')
const groupDesc = ref('')
const groupTags = ref('')
const creating = ref(false)
const message = ref('')
const msgType = ref('success')
const searchQuery = ref('')
const filterTag = ref('')
const editingTagsId = ref(null)
const editTagsValue = ref('')
const tagEditInput = ref(null)

async function applyFilters() {
  await store.fetchDatasets(filterTag.value || null, searchQuery.value || null)
}

function clearFilters() {
  searchQuery.value = ''
  filterTag.value = ''
  applyFilters()
}

function filterByTag(tag) {
  filterTag.value = tag
  applyFilters()
}

function startEditTags(d) {
  editingTagsId.value = d.id
  editTagsValue.value = (d.tags || []).join(', ')
  nextTick(() => {
    if (tagEditInput.value) {
      const el = Array.isArray(tagEditInput.value) ? tagEditInput.value[0] : tagEditInput.value
      if (el) el.focus()
    }
  })
}

async function saveTags(d) {
  const tags = editTagsValue.value.split(',').map(t => t.trim()).filter(Boolean)
  try {
    await store.updateTags(d.id, tags)
    message.value = `Tags updated for "${d.name}"`
    msgType.value = 'success'
    store.fetchTagSuggestions()
  } catch (e) {
    message.value = e.response?.data?.detail || 'Tag update failed'
    msgType.value = 'error'
  }
  editingTagsId.value = null
}

async function createGroup() {
  if (!groupName.value.trim()) return
  creating.value = true
  message.value = ''
  try {
    await store.createGroup(groupName.value.trim(), groupDesc.value.trim(), groupTags.value.trim())
    message.value = `Created "${groupName.value.trim()}"`
    msgType.value = 'success'
    groupName.value = ''
    groupDesc.value = ''
    groupTags.value = ''
    store.fetchTagSuggestions()
  } catch (e) {
    message.value = e.response?.data?.detail || 'Create failed'
    msgType.value = 'error'
  } finally {
    creating.value = false
  }
}

async function addFile(event, datasetId) {
  const file = event.target.files[0]
  if (!file) return
  try {
    await store.uploadFile(datasetId, file)
    message.value = `Added ${file.name}`
    msgType.value = 'success'
  } catch (e) {
    message.value = e.response?.data?.detail || 'Upload failed'
    msgType.value = 'error'
  }
  event.target.value = ''
}

async function deleteFile(ds, f) {
  if (!confirm(`Remove "${f.filename}" from "${ds.name}"?`)) return
  try {
    await store.deleteFile(ds.id, f.id)
    message.value = `Removed ${f.filename}`
    msgType.value = 'success'
  } catch (e) {
    message.value = e.response?.data?.detail || 'Delete failed'
    msgType.value = 'error'
  }
}

async function deleteDs(d) {
  if (!confirm(`Delete "${d.name}" and all its files? This removes it from all projects.`)) return
  try {
    await store.deleteDataset(d.id)
    message.value = `Deleted ${d.name}`
    msgType.value = 'success'
  } catch (e) {
    message.value = e.response?.data?.detail || 'Delete failed'
    msgType.value = 'error'
  }
}

function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString()
}

onMounted(() => {
  store.fetchDatasets()
  store.fetchTagSuggestions()
})
</script>

<style scoped>
.datasets h2 {
  margin-bottom: 1.5rem;
  color: var(--text-primary);
}

/* Filter bar */
.filter-bar {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
  align-items: center;
}

.search-input {
  flex: 1;
  min-width: 200px;
  padding: 0.45rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.85rem;
  background: var(--bg-input);
  color: var(--text-body);
}

.tag-filter {
  padding: 0.45rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.85rem;
  background: var(--bg-input);
  color: var(--text-body);
  min-width: 120px;
}

.clear-filter {
  padding: 0.45rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 0.8rem;
}
.clear-filter:hover { color: var(--text-primary); }

.create-form {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 2rem;
  align-items: center;
  flex-wrap: wrap;
}

.name-input {
  min-width: 180px;
  padding: 0.5rem 1rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.9rem;
  background: var(--bg-input);
  color: var(--text-body);
}

.desc-input {
  flex: 1;
  min-width: 160px;
  padding: 0.5rem 1rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.9rem;
  background: var(--bg-input);
  color: var(--text-body);
}

.tags-input {
  min-width: 180px;
  padding: 0.5rem 1rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.9rem;
  background: var(--bg-input);
  color: var(--text-body);
}

.create-form button {
  padding: 0.5rem 1.5rem;
  background: var(--accent);
  color: var(--accent-text);
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.9rem;
  white-space: nowrap;
}

.create-form button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.dataset-list {
  display: grid;
  gap: 1rem;
}

.dataset-card {
  background: var(--bg-card);
  border-radius: var(--card-radius, 12px);
  box-shadow: var(--card-shadow, 0 1px 3px rgba(0,0,0,0.06));
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: flex-start;
  padding: 1rem 1.25rem 0.75rem;
}

.card-content {
  flex: 1;
}

.card-content h3 {
  margin: 0 0 0.15rem;
  color: var(--text-primary);
  font-size: 1rem;
}

.desc {
  font-size: 0.82rem;
  color: var(--text-secondary);
  margin-bottom: 0.25rem;
}

/* Tags */
.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  align-items: center;
  margin: 0.35rem 0;
}

.tag-chip {
  display: inline-block;
  padding: 0.1rem 0.5rem;
  border-radius: 10px;
  font-size: 0.7rem;
  font-weight: 600;
  background: rgba(0, 191, 255, 0.12);
  color: var(--accent, #00BFFF);
  border: 1px solid rgba(0, 191, 255, 0.25);
  cursor: pointer;
  transition: background 0.15s;
}
.tag-chip:hover {
  background: rgba(0, 191, 255, 0.25);
}

.tag-edit-btn {
  display: inline-block;
  padding: 0 0.4rem;
  border: 1px dashed var(--border);
  border-radius: 10px;
  font-size: 0.7rem;
  color: var(--text-faint);
  background: none;
  cursor: pointer;
  line-height: 1.4;
}
.tag-edit-btn:hover { color: var(--text-secondary); border-color: var(--text-muted); }
.tag-edit-btn.add-first { font-size: 0.72rem; padding: 0.05rem 0.5rem; }

.tag-edit-input {
  flex: 1;
  min-width: 150px;
  padding: 0.2rem 0.5rem;
  border: 1px solid var(--accent, #00BFFF);
  border-radius: 4px;
  font-size: 0.78rem;
  background: var(--bg-input);
  color: var(--text-body);
}

.tag-save-btn, .tag-cancel-btn {
  padding: 0.15rem 0.5rem;
  border: none;
  border-radius: 4px;
  font-size: 0.72rem;
  cursor: pointer;
}
.tag-save-btn { background: var(--accent); color: var(--accent-text); }
.tag-cancel-btn { background: none; color: var(--text-muted); }

.meta {
  display: flex;
  gap: 1.5rem;
  font-size: 0.82rem;
  color: var(--text-muted);
}

.unused {
  color: var(--text-faint);
}

.delete-btn {
  background: none;
  border: none;
  font-size: 1.4rem;
  color: var(--text-faint);
  cursor: pointer;
  padding: 0 0.5rem;
  line-height: 1;
  flex-shrink: 0;
}

.delete-btn:hover {
  color: var(--danger);
}

/* File list within a dataset group */
.file-list {
  padding: 0 1.25rem;
}

.file-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.3rem 0.5rem;
  font-size: 0.82rem;
  border-top: 1px solid var(--border-lighter);
}

.file-name {
  color: var(--text-body);
  flex: 1;
}

.file-role {
  font-size: 0.7rem;
  padding: 0.05rem 0.35rem;
  border-radius: 3px;
  background: var(--badge-dataset, #e3f2fd);
  color: var(--badge-dataset-text, #1565c0);
  font-weight: 600;
  text-transform: uppercase;
}

.file-del {
  background: none;
  border: none;
  color: var(--text-faint);
  cursor: pointer;
  font-size: 1rem;
  padding: 0;
  line-height: 1;
}

.file-del:hover { color: var(--danger); }

.upload-into {
  display: block;
  padding: 0.5rem 1.25rem;
  font-size: 0.78rem;
  color: var(--text-muted);
  cursor: pointer;
  border-top: 1px solid var(--border-lighter);
  transition: background 0.15s;
}

.upload-into:hover {
  background: var(--bg-card-hover);
  color: var(--text-secondary);
}

.upload-into input[type="file"] { display: none; }

.msg {
  margin-top: 1rem;
  padding: 0.75rem 1rem;
  border-radius: 6px;
  font-size: 0.85rem;
}

.msg.success {
  background: var(--success-bg);
  color: var(--success-dark);
}

.msg.error {
  background: var(--danger-bg);
  color: var(--danger-dark);
}

.loading, .empty {
  text-align: center;
  padding: 3rem;
  color: var(--text-faint);
}
</style>
