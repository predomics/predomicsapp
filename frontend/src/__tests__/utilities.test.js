/**
 * Tests for utility modules: taxonomyColors.
 */
import { describe, it, expect } from 'vitest'
import {
  PHYLUM_PRIORITY_COLORS,
  MODULE_COLORS,
  lightenColor,
  darkenColor,
} from '../utils/taxonomyColors'

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
