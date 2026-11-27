import { ref, computed, watchEffect } from 'vue'

const MAX_BASKET_SIZE = 50

/**
 * Model Basket composable — manages a per-project collection of
 * bookmarked models, persisted to localStorage.
 */
export function useModelBasket(projectId) {
  const STORAGE_KEY = `predomics_basket_${projectId}`

  function loadBasket() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return []
      const parsed = JSON.parse(raw)
      if (parsed.version === 1) return parsed.items || []
      return []
    } catch {
      return []
    }
  }

  const basketItems = ref(loadBasket())

  watchEffect(() => {
    try {
      const payload = { version: 1, items: basketItems.value }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
    } catch { /* localStorage full — silent */ }
  })

  const basketCount = computed(() => basketItems.value.length)
  const basketFull = computed(() => basketItems.value.length >= MAX_BASKET_SIZE)

  const basketIdSet = computed(() =>
    new Set(basketItems.value.map(item => item.id))
  )

  function isInBasket(jobId, rank) {
    return basketIdSet.value.has(`${jobId}_rank_${rank}`)
  }

  function addToBasket(jobId, jobName, individual) {
    const id = `${jobId}_rank_${individual.rank}`
    if (basketIdSet.value.has(id)) return false
    if (basketItems.value.length >= MAX_BASKET_SIZE) return false

    basketItems.value.push({
      id,
      jobId,
      jobName: jobName || jobId.slice(0, 8),
      rank: individual.rank,
      addedAt: new Date().toISOString(),
      metrics: { ...individual.metrics },
      named_features: { ...(individual.named_features || {}) },
      // OR (clause) languages: keep the clause structure for display
      ...(individual.named_clauses ? { named_clauses: individual.named_clauses.map(c => ({ ...c, features: [...c.features] })) } : {}),
    })
    return true
  }

  function removeFromBasket(id) {
    basketItems.value = basketItems.value.filter(item => item.id !== id)
  }

  function clearBasket() {
    basketItems.value = []
  }

  function toggleBasket(jobId, jobName, individual) {
    const id = `${jobId}_rank_${individual.rank}`
    if (basketIdSet.value.has(id)) {
      removeFromBasket(id)
      return false
    } else {
      return addToBasket(jobId, jobName, individual)
    }
  }

  return {
    basketItems,
    basketCount,
    basketFull,
    isInBasket,
    addToBasket,
    removeFromBasket,
    clearBasket,
    toggleBasket,
    MAX_BASKET_SIZE,
  }
}
