/**
 * Tests for Vue composables.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'

// Mock window.matchMedia before importing composables
vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
  matches: false,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
}))

// ---------------------------------------------------------------------------
// useModelBasket
// ---------------------------------------------------------------------------
describe('useModelBasket', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.resetModules()
  })

  it('starts empty', async () => {
    const { useModelBasket } = await import('../composables/useModelBasket')
    const { basketItems, basketCount } = useModelBasket('proj1')
    expect(basketItems.value).toEqual([])
    expect(basketCount.value).toBe(0)
  })

  it('addToBasket adds a model and increments count', async () => {
    const { useModelBasket } = await import('../composables/useModelBasket')
    const { basketCount, addToBasket } = useModelBasket('proj1')
    const result = addToBasket('job1', 'Job 1', { rank: 0, metrics: { auc: 0.85 }, named_features: { f1: 1 } })
    expect(result).toBe(true)
    expect(basketCount.value).toBe(1)
  })

  it('isInBasket returns true for added model and false for others', async () => {
    const { useModelBasket } = await import('../composables/useModelBasket')
    const { addToBasket, isInBasket } = useModelBasket('proj1')
    addToBasket('job1', 'Job 1', { rank: 0, metrics: { auc: 0.85 }, named_features: { f1: 1 } })
    expect(isInBasket('job1', 0)).toBe(true)
    expect(isInBasket('job1', 1)).toBe(false)
  })

  it('removeFromBasket removes the item by id', async () => {
    const { useModelBasket } = await import('../composables/useModelBasket')
    const { basketCount, addToBasket, removeFromBasket } = useModelBasket('proj1')
    addToBasket('job1', 'Job 1', { rank: 0, metrics: { auc: 0.85 }, named_features: { f1: 1 } })
    expect(basketCount.value).toBe(1)
    removeFromBasket('job1_rank_0')
    expect(basketCount.value).toBe(0)
  })

  it('clearBasket removes all items', async () => {
    const { useModelBasket } = await import('../composables/useModelBasket')
    const { basketCount, addToBasket, clearBasket } = useModelBasket('proj1')
    addToBasket('job1', 'Job 1', { rank: 0, metrics: { auc: 0.85 }, named_features: {} })
    addToBasket('job2', 'Job 2', { rank: 0, metrics: { auc: 0.90 }, named_features: {} })
    addToBasket('job3', 'Job 3', { rank: 0, metrics: { auc: 0.75 }, named_features: {} })
    expect(basketCount.value).toBe(3)
    clearBasket()
    expect(basketCount.value).toBe(0)
  })

  it('toggleBasket adds if not present and removes if present', async () => {
    const { useModelBasket } = await import('../composables/useModelBasket')
    const { basketCount, isInBasket, toggleBasket } = useModelBasket('proj1')
    const individual = { rank: 0, metrics: { auc: 0.85 }, named_features: { f1: 1 } }

    // First toggle adds
    const added = toggleBasket('job1', 'Job 1', individual)
    expect(added).toBe(true)
    expect(basketCount.value).toBe(1)
    expect(isInBasket('job1', 0)).toBe(true)

    // Second toggle removes
    const removed = toggleBasket('job1', 'Job 1', individual)
    expect(removed).toBe(false)
    expect(basketCount.value).toBe(0)
    expect(isInBasket('job1', 0)).toBe(false)
  })

  it('basketFull is true when MAX_BASKET_SIZE items are added', async () => {
    const { useModelBasket } = await import('../composables/useModelBasket')
    const { basketFull, addToBasket, MAX_BASKET_SIZE } = useModelBasket('proj1')
    expect(MAX_BASKET_SIZE).toBe(50)

    for (let i = 0; i < MAX_BASKET_SIZE; i++) {
      addToBasket(`job${i}`, `Job ${i}`, { rank: 0, metrics: {}, named_features: {} })
    }
    expect(basketFull.value).toBe(true)

    // Adding one more should return false
    const result = addToBasket('jobExtra', 'Extra', { rank: 0, metrics: {}, named_features: {} })
    expect(result).toBe(false)
  })

  it('persists data to localStorage', async () => {
    const { useModelBasket } = await import('../composables/useModelBasket')
    const { addToBasket } = useModelBasket('proj1')
    addToBasket('job1', 'Job 1', { rank: 0, metrics: { auc: 0.85 }, named_features: { f1: 1 } })

    // watchEffect runs asynchronously — flush reactivity
    await nextTick()

    const raw = localStorage.getItem('predomics_basket_proj1')
    expect(raw).toBeTruthy()
    const parsed = JSON.parse(raw)
    expect(parsed.version).toBe(1)
    expect(parsed.items).toHaveLength(1)
    expect(parsed.items[0].id).toBe('job1_rank_0')
  })

  it('keeps baskets for different project IDs independent', async () => {
    const { useModelBasket } = await import('../composables/useModelBasket')
    const basket1 = useModelBasket('projA')
    const basket2 = useModelBasket('projB')

    basket1.addToBasket('job1', 'Job 1', { rank: 0, metrics: {}, named_features: {} })
    basket2.addToBasket('job2', 'Job 2', { rank: 0, metrics: {}, named_features: {} })
    basket2.addToBasket('job3', 'Job 3', { rank: 0, metrics: {}, named_features: {} })

    expect(basket1.basketCount.value).toBe(1)
    expect(basket2.basketCount.value).toBe(2)

    basket1.clearBasket()
    expect(basket1.basketCount.value).toBe(0)
    expect(basket2.basketCount.value).toBe(2)
  })
})

// ---------------------------------------------------------------------------
// useToast
// ---------------------------------------------------------------------------
describe('useToast', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.resetModules()
    vi.useRealTimers()
  })

  it('starts empty', async () => {
    const { useToast } = await import('../composables/useToast')
    const { toasts } = useToast()
    // Clear any leftover toasts from module-level state
    toasts.splice(0, toasts.length)
    expect(toasts).toHaveLength(0)
  })

  it('addToast adds a toast with correct message and type', async () => {
    const { useToast } = await import('../composables/useToast')
    const { toasts, addToast } = useToast()
    toasts.splice(0, toasts.length)

    addToast('Hello world', 'info', 0)
    expect(toasts).toHaveLength(1)
    expect(toasts[0].message).toBe('Hello world')
    expect(toasts[0].type).toBe('info')
  })

  it('addToast respects different types', async () => {
    const { useToast } = await import('../composables/useToast')
    const { toasts, addToast } = useToast()
    toasts.splice(0, toasts.length)

    addToast('Success!', 'success', 0)
    addToast('Error!', 'error', 0)
    addToast('Warning!', 'warning', 0)

    expect(toasts[0].type).toBe('success')
    expect(toasts[1].type).toBe('error')
    expect(toasts[2].type).toBe('warning')
  })

  it('removeToast removes the toast by id', async () => {
    const { useToast } = await import('../composables/useToast')
    const { toasts, addToast, removeToast } = useToast()
    toasts.splice(0, toasts.length)

    addToast('To be removed', 'info', 0)
    const id = toasts[0].id
    expect(toasts).toHaveLength(1)

    removeToast(id)
    expect(toasts).toHaveLength(0)
  })

  it('auto-removes toast after duration', async () => {
    vi.useFakeTimers()
    const { useToast } = await import('../composables/useToast')
    const { toasts, addToast } = useToast()
    toasts.splice(0, toasts.length)

    addToast('Temporary', 'info', 1000)
    expect(toasts).toHaveLength(1)

    vi.advanceTimersByTime(1000)
    expect(toasts).toHaveLength(0)
  })

  it('handles multiple toasts', async () => {
    const { useToast } = await import('../composables/useToast')
    const { toasts, addToast } = useToast()
    toasts.splice(0, toasts.length)

    addToast('First', 'info', 0)
    addToast('Second', 'success', 0)
    addToast('Third', 'error', 0)

    expect(toasts).toHaveLength(3)
    expect(toasts[0].message).toBe('First')
    expect(toasts[1].message).toBe('Second')
    expect(toasts[2].message).toBe('Third')
  })

  it('addToast with duration=0 does not auto-remove', async () => {
    vi.useFakeTimers()
    const { useToast } = await import('../composables/useToast')
    const { toasts, addToast } = useToast()
    toasts.splice(0, toasts.length)

    addToast('Permanent', 'info', 0)
    expect(toasts).toHaveLength(1)

    vi.advanceTimersByTime(10000)
    expect(toasts).toHaveLength(1)
  })
})

// ---------------------------------------------------------------------------
// useDebugMode
// ---------------------------------------------------------------------------
describe('useDebugMode', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.resetModules()
  })

  it('defaults to false', async () => {
    const { useDebugMode } = await import('../composables/useDebugMode')
    const { debugMode } = useDebugMode()
    expect(debugMode.value).toBe(false)
  })

  it('toggle switches between true and false', async () => {
    const { useDebugMode } = await import('../composables/useDebugMode')
    const { debugMode, toggle } = useDebugMode()

    toggle()
    expect(debugMode.value).toBe(true)

    toggle()
    expect(debugMode.value).toBe(false)
  })

  it('persists to localStorage', async () => {
    const { useDebugMode } = await import('../composables/useDebugMode')
    const { debugMode, toggle } = useDebugMode()

    toggle()
    expect(debugMode.value).toBe(true)

    // watchEffect runs asynchronously — flush reactivity
    await nextTick()
    expect(localStorage.getItem('debugMode')).toBe('true')
  })
})
