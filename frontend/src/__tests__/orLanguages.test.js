/**
 * OR (clause) languages in the frontend: model terms, chips, parameter form.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import i18n from '../i18n/index.js'
import { modelTerms, termsFromIndices, termLabel, coefLabel, formatModelFormula, isOrLanguage } from '../utils/modelTerms'
import { PARAM_DEFS } from '../data/parameterDefs'
import { validateForm } from '../utils/paramValidation'

const OR_MODEL = {
  rank: 3,
  metrics: { language: 'ternary-or', data_type: 'prev', auc: 0.9 },
  features: { 3: 1, 8: 1, 21: 1, 30: -1 },
  named_features: { f3: 1, f8: 1, f21: 1, f30: -1 },
  clauses: [[3, 8], [21], [30]],
  named_clauses: [
    { coef: 1, features: ['f3', 'f8'] },
    { coef: 1, features: ['f21'] },
    { coef: -1, features: ['f30'] },
  ],
}
const CLASSIC = { metrics: { language: 'ternary', data_type: 'raw' }, named_features: { b: 1, a: -1, c: 1 } }

describe('modelTerms', () => {
  it('one term per clause for an OR model, in clause order', () => {
    const terms = modelTerms(OR_MODEL)
    expect(terms.map(t => t.names)).toEqual([['f3', 'f8'], ['f21'], ['f30']])
    expect(terms.map(t => t.coef)).toEqual([1, 1, -1])
  })

  it('one term per feature for a classic model, negatives first then alphabetical', () => {
    expect(modelTerms(CLASSIC).map(t => `${t.names[0]}:${t.coef}`)).toEqual(['a:-1', 'b:1', 'c:1'])
  })

  it('handles missing data', () => {
    expect(modelTerms(null)).toEqual([])
    expect(modelTerms({})).toEqual([])
    expect(modelTerms({ named_clauses: [], named_features: { x: 1 } })).toHaveLength(1)
  })

  it('termsFromIndices groups indices by clause and resolves names', () => {
    const names = Array.from({ length: 40 }, (_, i) => `f${i}`)
    const terms = termsFromIndices({ 3: 1, 8: 1, 21: 1, 30: -1 }, [[3, 8], [21], [30]], names)
    expect(terms.map(t => termLabel(t))).toEqual(['f3 ∨ f8', 'f21', 'f30'])
    expect(terms[2].coef).toBe(-1)
    const classic = termsFromIndices({ '12': -1, '2': 1 }, null, names)
    expect(classic.map(t => t.names[0])).toEqual(['f2', 'f12'])
    expect(termsFromIndices({ 99: 1 }, null, names)[0].names).toEqual(['feature_99'])
  })

  it('labels', () => {
    expect(coefLabel(1)).toBe('+1')
    expect(coefLabel(-1)).toBe('-1')
    expect(coefLabel(2)).toBe('+2')
    expect(termLabel({ names: ['a', 'b'] }, n => n.toUpperCase())).toBe('A ∨ B')
    expect(isOrLanguage('ternary-or')).toBe(true)
    expect(isOrLanguage('ternary')).toBe(false)
  })

  it('formatModelFormula', () => {
    expect(formatModelFormula(OR_MODEL)).toBe('((f3⁰ ∨ f8⁰) + f21⁰) - f30⁰')
    expect(formatModelFormula(CLASSIC)).toBe('(b + c) - a')
    expect(formatModelFormula({ metrics: { language: 'ratio-or', data_type: 'raw' },
      named_clauses: [{ coef: 1, features: ['A', 'B'] }, { coef: -1, features: ['C'] }] })).toBe('(A ∨ B) / (C + ε)')
    expect(formatModelFormula({ metrics: { language: 'pow2', data_type: 'log' }, named_features: { A: 2, B: -1 } })).toBe('2*ln(A) - ln(B)')
    expect(formatModelFormula({ metrics: { language: 'binary' }, named_features: { A: 1 } })).toBe('A')
    expect(formatModelFormula({ metrics: { language: 'binary-or' }, named_features: { A: 1, B: 1, C: 1 },
      named_clauses: [{ coef: 1, features: ['A', 'B'] }, { coef: 1, features: ['C'] }] })).toBe('(A ∨ B) + C')
    expect(formatModelFormula({})).toBe('')
  })
})

describe('ModelTerms component', () => {
  it('renders one chip per clause with the OR sign and the real coefficient', async () => {
    const { default: ModelTerms } = await import('../components/results/ModelTerms.vue')
    const wrapper = mount(ModelTerms, { props: { model: OR_MODEL, labelOf: n => n.toUpperCase() } })
    const chips = wrapper.findAll('.feature-chip')
    expect(chips).toHaveLength(3)
    expect(chips[0].classes()).toContain('clause')
    expect(chips[0].classes()).toContain('positive')
    expect(chips[0].text()).toBe('F3 ∨ F8 (+1)')
    expect(chips[1].classes()).not.toContain('clause')
    expect(chips[2].classes()).toContain('negative')
    expect(chips[2].text()).toBe('F30 (-1)')
  })

  it('shows classic models as before', async () => {
    const { default: ModelTerms } = await import('../components/results/ModelTerms.vue')
    const wrapper = mount(ModelTerms, { props: { model: CLASSIC } })
    expect(wrapper.findAll('.feature-chip').map(c => c.text())).toEqual(['a (-1)', 'b (+1)', 'c (+1)'])
  })
})

describe('model basket keeps clauses', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('copies named_clauses when present', async () => {
    const { useModelBasket } = await import('../composables/useModelBasket')
    const { basketItems, addToBasket } = useModelBasket('projOr')
    addToBasket('job1', 'Job 1', OR_MODEL)
    addToBasket('job1', 'Job 1', { ...CLASSIC, rank: 4 })
    expect(basketItems.value[0].named_clauses).toEqual(OR_MODEL.named_clauses)
    expect(basketItems.value[0].named_clauses).not.toBe(OR_MODEL.named_clauses)
    expect(basketItems.value[1]).not.toHaveProperty('named_clauses')
  })
})

describe('parameter form', () => {
  const languageDef = PARAM_DEFS.find(p => p.category === 'general' && p.key === 'language')
  const algoDef = PARAM_DEFS.find(p => p.category === 'general' && p.key === 'algo')
  const clauseDef = PARAM_DEFS.find(p => p.category === 'beam' && p.key === 'max_clause_size')

  it('offers the OR languages, tied to the Beam algorithm', () => {
    const or = languageDef.options.filter(o => o.value.endsWith('-or'))
    expect(or.map(o => o.value)).toEqual(['bin-or', 'ter-or', 'ratio-or'])
    for (const o of or) expect(o.onlyWith).toEqual({ key: 'algo', values: ['beam'], hint: 'parameters.beamOnly' })
    expect(languageDef.options.some(o => o.value === 'pow2-or')).toBe(false)
    expect(clauseDef).toBeTruthy()
    expect(clauseDef.defaultValue).toBe(3)
    expect(clauseDef.min).toBe(0)
  })

  it('validateForm reports an OR language picked with another algorithm', () => {
    const defs = [algoDef, languageDef]
    const bad = validateForm({ general: { algo: 'ga', language: 'bin,ter-or' } }, defs)
    expect(bad['general.language']).toEqual({
      code: 'onlyWith', params: { option: 'Ternary-OR', other: 'algo', values: 'beam' },
    })
    expect(validateForm({ general: { algo: 'beam', language: 'bin,ter-or' } }, defs)).toEqual({})
    expect(validateForm({ general: { algo: 'ga', language: 'bin,ter' } }, defs)).toEqual({})
  })

  it('ParamField disables unavailable options and keeps a picked one clearable', async () => {
    const { default: ParamField } = await import('../components/ParamField.vue')
    const mountWith = form => mount(ParamField, { props: { def: languageDef, form }, global: { plugins: [i18n] } })
    const byValue = (wrapper, value) => wrapper.findAll('.checkbox-group-item')[languageDef.options.findIndex(o => o.value === value)]

    let w = mountWith({ algo: 'ga', language: 'bin' })
    expect(byValue(w, 'ter-or').classes()).toContain('unavailable')
    expect(byValue(w, 'ter-or').find('input').attributes('disabled')).toBeDefined()
    expect(byValue(w, 'ter-or').attributes('title')).toContain('Beam')
    expect(byValue(w, 'ter').classes()).not.toContain('unavailable')
    expect(byValue(w, 'ter').find('input').attributes('disabled')).toBeUndefined()

    w = mountWith({ algo: 'beam', language: 'bin' })
    expect(byValue(w, 'ter-or').classes()).not.toContain('unavailable')
    expect(byValue(w, 'ter-or').find('input').attributes('disabled')).toBeUndefined()

    const form = { algo: 'ga', language: 'bin,ter-or' }
    w = mountWith(form)
    const item = byValue(w, 'ter-or')
    expect(item.classes()).toContain('unavailable')
    expect(item.find('input').attributes('disabled')).toBeUndefined()
    await item.find('input').trigger('change')
    expect(form.language).toBe('bin')
  })

  it('translates the new keys', () => {
    const { t, te } = i18n.global
    for (const key of ['params.general.language.opt.ter-or', 'params.beam.max_clause_size.label', 'paramErrors.onlyWith', 'parameters.beamOnly']) {
      expect(te(key), key).toBe(true)
    }
    expect(t('paramErrors.onlyWith', { option: 'Ternary-OR', other: 'Algorithm', values: 'beam' })).toContain('Ternary-OR')
  })
})

describe('ModelFormula component (best model as a rule)', () => {
  const BEST = {
    k: 4, auc: 0.9, threshold: 1.5, language: 'Ternary-OR', data_type: 'prev',
    features: { 3: 1, 8: 1, 21: 1, 30: -1 }, clauses: [[3, 8], [21], [30]],
  }
  const NAMES = Array.from({ length: 40 }, (_, i) => `f${i}`)

  it('shows positive and negative terms, the decision and the exact formula', async () => {
    const { default: ModelFormula } = await import('../components/results/ModelFormula.vue')
    const wrapper = mount(ModelFormula, {
      global: { plugins: [i18n] },
      props: { model: BEST, featureNames: NAMES, classNameFor: c => (c === 1 ? 'Cirrhosis' : 'Healthy') },
    })
    expect(wrapper.findAll('.rule-side.positive .rule-chip').map(c => c.text())).toEqual(['f3 ∨ f8', 'f21'])
    expect(wrapper.findAll('.rule-side.negative .rule-chip').map(c => c.text())).toEqual(['f30'])
    expect(wrapper.find('.rule-op').text()).toBe('−')
    expect(wrapper.find('.formula-text').text()).toBe('((f3⁰ ∨ f8⁰) + f21⁰) - f30⁰ ≥ 1.5')
    const decision = wrapper.find('.rule-decision').text()
    expect(decision).toContain('Cirrhosis')
    expect(decision).toContain('score ≥ 1.5')
    expect(decision).toContain('Healthy')
    expect(wrapper.find('.rule-meta').text()).toBe('Ternary-OR · prev · 4 features in 3 terms')
    expect(wrapper.findAll('.rule-legend li')).toHaveLength(3)
  })

  it('writes a ratio model as a fraction with ε and a binary model without a negative side', async () => {
    const { default: ModelFormula } = await import('../components/results/ModelFormula.vue')
    const ratio = mount(ModelFormula, {
      global: { plugins: [i18n] },
      props: { model: { language: 'ratio', data_type: 'raw', threshold: 1, features: { 0: 1, 1: -1 } }, featureNames: ['a', 'b'] },
    })
    expect(ratio.find('.rule-visual').classes()).toContain('ratio')
    expect(ratio.find('.rule-chip.epsilon').exists()).toBe(true)
    expect(ratio.find('.formula-text').text()).toBe('a / (b + ε) ≥ 1')

    const binary = mount(ModelFormula, {
      global: { plugins: [i18n] },
      props: { model: { language: 'bin', data_type: 'prev', threshold: 2, features: { 0: 1, 1: 1 } }, featureNames: ['a', 'b'], isRegression: true },
    })
    expect(binary.find('.rule-side.negative').exists()).toBe(false)
    expect(binary.find('.rule-decision').exists()).toBe(false)
    expect(binary.find('.formula-text').text()).toBe('a⁰ + b⁰')
  })
})
