/**
 * Tests for parameterDefs data — ensures integrity of the parameter definition registry.
 */
import { describe, it, expect } from 'vitest'
import { PARAM_DEFS, CATEGORIES } from '../data/parameterDefs'

describe('CATEGORIES', () => {
  it('should have at least 5 categories', () => {
    expect(CATEGORIES.length).toBeGreaterThanOrEqual(5)
  })

  it('each category has id and label', () => {
    for (const cat of CATEGORIES) {
      expect(cat.id).toBeTruthy()
      expect(cat.label).toBeTruthy()
    }
  })

  it('category IDs are unique', () => {
    const ids = CATEGORIES.map(c => c.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('includes required categories', () => {
    const ids = CATEGORIES.map(c => c.id)
    expect(ids).toContain('general')
    expect(ids).toContain('ga')
    expect(ids).toContain('beam')
    expect(ids).toContain('mcmc')
    expect(ids).toContain('cv')
  })
})

describe('PARAM_DEFS', () => {
  it('should have a substantial number of parameters', () => {
    expect(PARAM_DEFS.length).toBeGreaterThanOrEqual(40)
  })

  it('each parameter has required fields', () => {
    for (const p of PARAM_DEFS) {
      expect(p.key).toBeTruthy()
      expect(p.label).toBeTruthy()
      expect(p.category).toBeTruthy()
      expect(p.level).toBeTruthy()
      expect(p.inputType).toBeTruthy()
      expect(p).toHaveProperty('defaultValue')
      expect(p.description).toBeTruthy()
    }
  })

  it('every param category exists in CATEGORIES', () => {
    const catIds = new Set(CATEGORIES.map(c => c.id))
    for (const p of PARAM_DEFS) {
      expect(catIds.has(p.category)).toBe(true)
    }
  })

  it('level is either basic or advanced', () => {
    for (const p of PARAM_DEFS) {
      expect(['basic', 'advanced']).toContain(p.level)
    }
  })

  it('inputType is a valid type', () => {
    const validTypes = ['text', 'number', 'select', 'checkbox', 'checkboxGroup']
    for (const p of PARAM_DEFS) {
      expect(validTypes).toContain(p.inputType)
    }
  })

  it('select and checkboxGroup inputs have options array', () => {
    for (const p of PARAM_DEFS) {
      if (p.inputType === 'select' || p.inputType === 'checkboxGroup') {
        expect(Array.isArray(p.options)).toBe(true)
        expect(p.options.length).toBeGreaterThan(0)
        for (const opt of p.options) {
          expect(opt.value).toBeDefined()
          expect(opt.label).toBeTruthy()
        }
      }
    }
  })

  it('checkbox defaults are boolean', () => {
    for (const p of PARAM_DEFS) {
      if (p.inputType === 'checkbox') {
        expect(typeof p.defaultValue).toBe('boolean')
      }
    }
  })

  it('number defaults are numbers', () => {
    for (const p of PARAM_DEFS) {
      if (p.inputType === 'number') {
        // null = "no limit / automatic" (e.g. tree depth): the field may stay empty
        if (p.defaultValue === null) continue
        expect(typeof p.defaultValue).toBe('number')
      }
    }
  })

  it('contains key general parameters', () => {
    const keys = PARAM_DEFS.map(p => `${p.category}.${p.key}`)
    expect(keys).toContain('general.algo')
    expect(keys).toContain('general.fit')
    expect(keys).toContain('general.language')
    expect(keys).toContain('general.seed')
    expect(keys).toContain('ga.population_size')
    expect(keys).toContain('ga.max_epochs')
    expect(keys).toContain('ga.k_min')
    expect(keys).toContain('ga.k_max')
  })
})
