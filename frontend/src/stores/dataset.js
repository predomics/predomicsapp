import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export const useDatasetStore = defineStore('dataset', () => {
  const datasets = ref([])
  const loading = ref(false)
  const tagSuggestions = ref([])

  async function fetchDatasets(tag = null, search = null) {
    loading.value = true
    try {
      const params = {}
      if (tag) params.tag = tag
      if (search) params.search = search
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
    const idx = datasets.value.findIndex(d => d.id === datasetId)
    if (idx >= 0) {
      datasets.value[idx].files.push(data)
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

  async function assignDataset(datasetId, projectId) {
    await axios.post(`/api/datasets/${datasetId}/assign/${projectId}`)
  }

  async function unassignDataset(datasetId, projectId) {
    await axios.delete(`/api/datasets/${datasetId}/assign/${projectId}`)
  }

  return {
    datasets, loading, tagSuggestions,
    fetchDatasets, fetchTagSuggestions, createGroup, updateTags,
    uploadFile, deleteFile, deleteDataset, assignDataset, unassignDataset,
  }
})
