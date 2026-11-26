import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'

export const useProjectStore = defineStore('project', () => {
  const projects = ref([])
  const sharedProjects = ref([])
  const current = ref(null)
  const selectedId = ref(null)
  const activeJobId = ref(null)
  const showConsole = ref(false)
  const dataFilters = ref({
    std_threshold: null,
    prevalence_min_pct: 10,
    top_n_significant: null,
    method: 'wilcoxon',
  })

  async function fetchAll(includeArchived = false) {
    const { data } = await api.projects.list({
      params: { include_archived: includeArchived },
    })
    projects.value = data
  }

  async function fetchSharedProjects() {
    try {
      const { data } = await api.projects.sharedWithMe({ silentError: true })
      sharedProjects.value = data
    } catch { /* optional list: the page still works without it */ }
  }

  async function fetchOne(id) {
    const { data } = await api.projects.get(id)
    current.value = data
    return data
  }

  async function create(name, description = '') {
    const { data } = await api.projects.create(null, { params: { name, description } })
    await fetchAll()
    return data
  }

  async function updateProject(id, { name, description, class_names } = {}) {
    const body = {}
    if (name !== undefined) body.name = name
    if (description !== undefined) body.description = description
    if (class_names !== undefined) body.class_names = class_names
    const { data } = await api.projects.update(id, body)
    const idx = projects.value.findIndex(p => p.project_id === id)
    if (idx >= 0) projects.value[idx] = data
    if (current.value?.project_id === id) current.value = data
    return data
  }

  async function remove(id) {
    await api.projects.remove(id)
    if (selectedId.value === id) selectedId.value = null
    await fetchAll()
  }

  async function archiveProject(id) {
    const { data } = await api.projects.toggleArchive(id)
    const idx = projects.value.findIndex(p => p.project_id === id)
    if (idx >= 0) projects.value[idx] = data
    return data
  }

  function startJob(jobId) {
    activeJobId.value = jobId
    showConsole.value = true
  }

  function closeConsole() {
    showConsole.value = false
  }

  return {
    projects, sharedProjects, current, selectedId,
    activeJobId, showConsole, dataFilters,
    fetchAll, fetchSharedProjects, fetchOne, create, updateProject, remove,
    archiveProject, startJob, closeConsole,
  }
})
