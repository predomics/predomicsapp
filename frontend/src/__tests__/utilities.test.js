/**
 * Tests for utility modules: retry and taxonomyColors.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { withRetry } from '../utils/retry'
import {
  PHYLUM_PRIORITY_COLORS,
  MODULE_COLORS,
  lightenColor,
  darkenColor,
} from '../utils/taxonomyColors'

// ---------------------------------------------------------------------------
// retry.js
// ---------------------------------------------------------------------------
describe('withRetry', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns result on first try when fn succeeds immediately', async () => {
    const fn = vi.fn().mockResolvedValue('ok')
    const result = await withRetry(fn)
    expect(result).toBe('ok')
    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('retries and returns result when fn fails then succeeds', async () => {
    const fn = vi.fn()
      .mockRejectedValueOnce(new Error('fail 1'))
      .mockRejectedValueOnce(new Error('fail 2'))
      .mockResolvedValue('success')

    const promise = withRetry(fn, { delay: 100 })

    // First retry delay: 100 * 1 = 100
    await vi.advanceTimersByTimeAsync(100)
    // Second retry delay: 100 * 2 = 200
    await vi.advanceTimersByTimeAsync(200)

    const result = await promise
    expect(result).toBe('success')
    expect(fn).toHaveBeenCalledTimes(3)
  })

  it('throws after max retries are exhausted', async () => {
    const error = new Error('always fails')
    const fn = vi.fn().mockRejectedValue(error)

    const promise = withRetry(fn, { retries: 3, delay: 100 })
    // Attach a no-op catch so the intermediate rejections don't surface as unhandled
    promise.catch(() => {})

    // Advance through all retry delays: 100, 200, 300
    await vi.advanceTimersByTimeAsync(100)
    await vi.advanceTimersByTimeAsync(200)
    await vi.advanceTimersByTimeAsync(300)

    await expect(promise).rejects.toThrow('always fails')
    expect(fn).toHaveBeenCalledTimes(4) // 1 initial + 3 retries
  })

  it('does not retry on 4xx errors', async () => {
    const error = new Error('bad request')
    error.response = { status: 400 }
    const fn = vi.fn().mockRejectedValue(error)

    await expect(withRetry(fn)).rejects.toThrow('bad request')
    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('retries on 5xx errors then succeeds', async () => {
    const serverError = new Error('server error')
    serverError.response = { status: 500 }
    const fn = vi.fn()
      .mockRejectedValueOnce(serverError)
      .mockResolvedValue('recovered')

    const promise = withRetry(fn, { delay: 100 })

    // First retry delay: 100 * 1 = 100
    await vi.advanceTimersByTimeAsync(100)

    const result = await promise
    expect(result).toBe('recovered')
    expect(fn).toHaveBeenCalledTimes(2)
  })

  it('respects custom retry count', async () => {
    const error = new Error('fail')
    const fn = vi.fn().mockRejectedValue(error)

    const promise = withRetry(fn, { retries: 1, delay: 100 })
    promise.catch(() => {})

    // One retry delay: 100 * 1 = 100
    await vi.advanceTimersByTimeAsync(100)

    await expect(promise).rejects.toThrow('fail')
    expect(fn).toHaveBeenCalledTimes(2) // 1 initial + 1 retry
  })

  it('uses exponential delay between retries', async () => {
    const error = new Error('fail')
    const fn = vi.fn().mockRejectedValue(error)
    const delay = 1000

    const promise = withRetry(fn, { retries: 3, delay })
    promise.catch(() => {})

    // After first failure, delay is delay * 1 = 1000
    expect(fn).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(999)
    expect(fn).toHaveBeenCalledTimes(1) // not yet retried
    await vi.advanceTimersByTimeAsync(1)
    expect(fn).toHaveBeenCalledTimes(2) // retried after 1000ms

    // After second failure, delay is delay * 2 = 2000
    await vi.advanceTimersByTimeAsync(1999)
    expect(fn).toHaveBeenCalledTimes(2) // not yet retried
    await vi.advanceTimersByTimeAsync(1)
    expect(fn).toHaveBeenCalledTimes(3) // retried after 2000ms

    // After third failure, delay is delay * 3 = 3000
    await vi.advanceTimersByTimeAsync(2999)
    expect(fn).toHaveBeenCalledTimes(3) // not yet retried
    await vi.advanceTimersByTimeAsync(1)
    expect(fn).toHaveBeenCalledTimes(4) // retried after 3000ms

    // Promise should now reject since retries are exhausted
    await expect(promise).rejects.toThrow('fail')
  })
})

// ---------------------------------------------------------------------------
// taxonomyColors.js
// ---------------------------------------------------------------------------
describe('taxonomyColors', () => {
  const hexPattern = /^#[0-9a-f]{6}$/i

  describe('PHYLUM_PRIORITY_COLORS', () => {
    it('has expected phyla as keys', () => {
      expect(PHYLUM_PRIORITY_COLORS).toHaveProperty('Bacillota')
      expect(PHYLUM_PRIORITY_COLORS).toHaveProperty('Bacteroidota')
      expect(PHYLUM_PRIORITY_COLORS).toHaveProperty('Pseudomonadota')
    })

    it('values are valid hex colors', () => {
      for (const color of Object.values(PHYLUM_PRIORITY_COLORS)) {
        expect(color).toMatch(hexPattern)
      }
    })
  })

  describe('MODULE_COLORS', () => {
    it('has 12 entries that are all hex colors', () => {
      expect(MODULE_COLORS).toHaveLength(12)
      for (const color of MODULE_COLORS) {
        expect(color).toMatch(hexPattern)
      }
    })
  })

  describe('lightenColor', () => {
    it('makes a color lighter', () => {
      const result = lightenColor('#000000')
      const [r, g, b] = hexToRgbHelper(result)
      expect(r).toBeGreaterThan(0)
      expect(g).toBeGreaterThan(0)
      expect(b).toBeGreaterThan(0)
    })

    it('keeps white as white', () => {
      expect(lightenColor('#ffffff')).toBe('#ffffff')
    })

    it('accepts a custom amount', () => {
      const result = lightenColor('#000000', 0.5)
      // 0 + (255 - 0) * 0.5 = 127.5 → rounds to 128 → hex 80
      expect(result.toLowerCase()).toBe('#808080')
    })
  })

  describe('darkenColor', () => {
    it('makes a color darker', () => {
      const result = darkenColor('#ffffff')
      const [r, g, b] = hexToRgbHelper(result)
      expect(r).toBeLessThan(255)
      expect(g).toBeLessThan(255)
      expect(b).toBeLessThan(255)
    })

    it('keeps black as black', () => {
      expect(darkenColor('#000000')).toBe('#000000')
    })

    it('accepts a custom amount', () => {
      const result = darkenColor('#ffffff', 0.5)
      // 255 * (1 - 0.5) = 127.5 → rounds to 128 → hex 80
      expect(result.toLowerCase()).toBe('#808080')
    })
  })

  describe('roundtrip consistency', () => {
    it('lightening then darkening returns a value close to the original', () => {
      const original = '#808080'
      const lightened = lightenColor(original, 0.2)
      const restored = darkenColor(lightened, 0.2)

      // lighten then darken are not exact inverses, so allow a reasonable
      // tolerance per channel.  For mid-grey with a small amount the drift
      // stays within ~10 per channel.
      const [oR, oG, oB] = hexToRgbHelper(original)
      const [rR, rG, rB] = hexToRgbHelper(restored)
      expect(Math.abs(oR - rR)).toBeLessThanOrEqual(10)
      expect(Math.abs(oG - rG)).toBeLessThanOrEqual(10)
      expect(Math.abs(oB - rB)).toBeLessThanOrEqual(10)
    })
  })
})

// ---------------------------------------------------------------------------
// Test helper — mirrors the internal hexToRgb from taxonomyColors.js
// ---------------------------------------------------------------------------
function hexToRgbHelper(hex) {
  const h = hex.replace('#', '')
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]
}
