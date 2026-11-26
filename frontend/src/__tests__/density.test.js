import { describe, it, expect } from 'vitest'
import { densityGrid } from '../utils/density'

describe('densityGrid', () => {
  it('counts points per bin and leaves empty bins null', () => {
    const g = densityGrid([1, 1, 1, 5], [0.1, 0.1, 0.1, 0.9], { nx: 5, ny: 2, integerX: true })
    expect(g.x).toEqual([1, 2, 3, 4, 5]) // one bin per integer k
    expect(g.y).toHaveLength(2)
    expect(g.z[0][0]).toBe(3)
    expect(g.z[1][4]).toBe(1)
    expect(g.z[0][2]).toBeNull()
    expect(g.max).toBe(3)
    const total = g.z.flat().reduce((s, v) => s + (v || 0), 0)
    expect(total).toBe(4)
  })
  it('groups integers when there are more values than bins', () => {
    const ks = Array.from({ length: 100 }, (_, i) => i + 1)
    const g = densityGrid(ks, ks.map(() => 0.5), { nx: 40, integerX: true })
    expect(g.x.length).toBeLessThanOrEqual(40)
    expect(g.z.flat().reduce((s, v) => s + (v || 0), 0)).toBe(100)
  })
  it('handles a single value and bad input', () => {
    expect(densityGrid([3], [0.7]).max).toBe(1)
    expect(densityGrid([], [])).toEqual({ x: [], y: [], z: [], max: 0 })
    expect(densityGrid([1, NaN], [0.5, 0.5]).max).toBe(1)
  })
})
