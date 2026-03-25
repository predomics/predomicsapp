import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export const useDatasetStore = defineStore('dataset', () => {
  const datasets = ref([])
  const loading = ref(false)
  const tagSuggestions = ref([])
  const metadata_columns = ref([])
  const selected_y_column = ref(null)

  async function fetchDatasets(tag = null, search = null, includeArchived = false) {
    loading.value = true
    try {
      const params = {}
      if (tag) params.tag = tag
      if (search) params.search = search
      if (includeArchived) params.include_archived = true
      const { data } = await axios.get('/api/datasets/', { params })
      datasets.value = data
    } finally {
      loading.value = false
    }
  }

  async function fetchTagSuggestions() {
    try {
      const { data } = await axios.get('/api/datasets/tags/suggestions')
      tagSuggestions.value = data.suggestions || []
    } catch { /* ignore */ }
  }

  async function createGroup(name, description = '', tags = '') {
    const { data } = await axios.post('/api/datasets/', null, {
      params: { name, description, tags },
    })
    datasets.value.unshift(data)
    return data
  }

  async function updateTags(datasetId, tags) {
    const { data } = await axios.patch(`/api/datasets/${datasetId}/tags`, { tags })
    const idx = datasets.value.findIndex(d => d.id === datasetId)
    if (idx >= 0) {
      datasets.value[idx].tags = data.tags
    }
    return data
  }

  async function uploadFile(datasetId, file, role = null) {
    const form = new FormData()
    form.append('file', file)
    const params = {}
    if (role) params.role = role
    const { data } = await axios.post(`/api/datasets/${datasetId}/files`, form, { params })
    // Refresh full dataset to pick up auto-scanned metadata
    await refreshDataset(datasetId)
    return data
  }

  async function refreshDataset(datasetId) {
    try {
      const { data } = await axios.get(`/api/datasets/${datasetId}`)
      const idx = datasets.value.findIndex(d => d.id === datasetId)
      if (idx >= 0) datasets.value[idx] = data
    } catch { /* ignore */ }
  }

  async function scanDataset(datasetId) {
    const { data } = await axios.post(`/api/datasets/${datasetId}/scan`)
    const idx = datasets.value.findIndex(d => d.id === datasetId)
    if (idx >= 0) {
      datasets.value[idx].metadata = data
    }
    return data
  }

  async function deleteFile(datasetId, fileId) {
    await axios.delete(`/api/datasets/${datasetId}/files/${fileId}`)
    const idx = datasets.value.findIndex(d => d.id === datasetId)
    if (idx >= 0) {
      datasets.value[idx].files = datasets.value[idx].files.filter(f => f.id !== fileId)
    }
  }

  async function deleteDataset(id) {
    await axios.delete(`/api/datasets/${id}`)
    datasets.value = datasets.value.filter(d => d.id !== id)
  }

  async function updateDataset(id, { name, description } = {}) {
    const body = {}
    if (name !== undefined) body.name = name
    if (description !== undefined) body.description = description
    const { data } = await axios.patch(`/api/datasets/${id}`, body)
    const idx = datasets.value.findIndex(d => d.id === id)
    if (idx >= 0) datasets.value[idx] = data
    return data
  }

  async function archiveDataset(id) {
    const { data } = await axios.post(`/api/datasets/${id}/archive`)
    const idx = datasets.value.findIndex(d => d.id === id)
    if (idx >= 0) datasets.value[idx] = data
    return data
  }

  async function updateClassNames(datasetId, classNames) {
    const { data } = await axios.patch(`/api/datasets/${datasetId}/class-names`, { class_names: classNames })
    const idx = datasets.value.findIndex(d => d.id === datasetId)
    if (idx >= 0 && datasets.value[idx].metadata) {
      datasets.value[idx].metadata.class_names = data.class_names
    }
    return data
  }

  async function assignDataset(datasetId, projectId) {
    await axios.post(`/api/datasets/${datasetId}/assign/${projectId}`)
  }

  async function unassignDataset(datasetId, projectId) {
    await axios.delete(`/api/datasets/${datasetId}/assign/${projectId}`)
  }

  async function fetchMetadataColumns(projectId, datasetId, fileId) {
    try {
      const { data } = await axios.get(
        `/api/projects/${projectId}/datasets/${datasetId}/files/${fileId}/columns`
      )
      metadata_columns.value = data.numeric_columns || []
    } catch {
      metadata_columns.value = []
    }
    return metadata_columns.value
  }

  function setSelectedYColumn(column) {
    selected_y_column.value = column
  }

  return {
    datasets, loading, tagSuggestions, metadata_columns, selected_y_column,
    fetchDatasets, fetchTagSuggestions, createGroup, updateDataset, updateTags,
    uploadFile, deleteFile, deleteDataset, archiveDataset, assignDataset, unassignDataset,
    refreshDataset, scanDataset, updateClassNames, fetchMetadataColumns, setSelectedYColumn,
  }
})
