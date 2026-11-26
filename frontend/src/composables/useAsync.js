/**
 * Run an async loader and expose { loading, error, run } for <AsyncState>.
 *
 *   const { loading, error, run } = useAsync(() => api.projects.list())
 *   onMounted(run)            // <AsyncState :loading :error :retry="run">
 */
import { ref } from 'vue'
import { apiError } from '../utils/apiError'

export function useAsync(fn, { fallback = '' } = {}) {
  const loading = ref(false)
  const error = ref('')
  let seq = 0

  async function run(...args) {
    const mine = ++seq
    loading.value = true
    error.value = ''
    try {
      return await fn(...args)
    } catch (e) {
      if (mine === seq) error.value = apiError(e, fallback)
      return undefined
    } finally {
      if (mine === seq) loading.value = false
    }
  }

  return { loading, error, run }
}
