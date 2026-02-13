import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export const useProjectStore = defineStore('project', () => {
  const projects = ref([])
  const current = ref(null)
  const activeJobId = ref(null)
  const showConsole = ref(false)
  const dataFilters = ref({
    std_threshold: null,
    prevalence_min_pct: 10,
    top_n_significant: null,
    method: 'wilcoxon',
  })

  async function fetchAll() {
    const { data } = await axios.get('/api/projects/')
    projects.value = data
  }

  async function fetchOne(id) {
    const { data } = await axios.get(`/api/projects/${id}`)
    current.value = data
    return data
  }

  async function create(name) {
    const { data } = await axios.post('/api/projects/', null, { params: { name } })
    await fetchAll()
    return data
  }

  async function remove(id) {
    await axios.delete(`/api/projects/${id}`)
    await fetchAll()
  }

  function startJob(jobId) {
    activeJobId.value = jobId
    showConsole.value = true
  }

  function closeConsole() {
    showConsole.value = false
  }

  return {
    projects, current, activeJobId, showConsole, dataFilters,
    fetchAll, fetchOne, create, remove, startJob, closeConsole,
  }
})
