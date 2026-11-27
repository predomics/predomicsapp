/**
 * Terms of a BTR model, for display.
 *
 * A classic model has one term per feature (`named_features`: name -> coefficient).
 * A model of an OR (clause) language (binary-or, ternary-or, ratio-or) has one
 * term per clause (`named_clauses`: [{ coef, features: [names] }]); the clause is
 * true when any of its features is, and is written "A ∨ B".
 *
 * Each term is { key, names: [string], coef: number }.
 */

export const OR_SIGN = '∨' // ∨

function isOrLanguage(language) {
  const l = String(language || '').toLowerCase()
  return l.endsWith('-or') || l.endsWith('_or')
}

/** Negative terms first, then alphabetical: the order the population view always used. */
function classicOrder(a, b) {
  if (a.coef !== b.coef) return a.coef - b.coef
  return a.names[0].localeCompare(b.names[0])
}

/**
 * Terms of a model from the results JSON (population entry, basket item or
 * best_individual with `named_features`).
 */
export function modelTerms(model) {
  if (!model) return []
  const clauses = Array.isArray(model.named_clauses) ? model.named_clauses : null
  if (clauses && clauses.length) {
    // keep the engine's canonical clause order
    return clauses
      .filter(c => c && Array.isArray(c.features) && c.features.length)
      .map(c => ({ key: c.features.join('|'), names: c.features.map(String), coef: Number(c.coef) || 0 }))
  }
  const named = model.named_features || {}
  return Object.entries(named)
    .map(([name, coef]) => ({ key: name, names: [name], coef: Number(coef) || 0 }))
    .sort(classicOrder)
}

/**
 * Terms from index-based data (`best_individual.features`: index -> coefficient,
 * optional `clauses`: [[index]]) and the job's feature names.
 */
export function termsFromIndices(features, clauses, featureNames) {
  const feats = features || {}
  const names = featureNames || []
  const nameOf = idx => names[Number(idx)] ?? `feature_${idx}`
  if (Array.isArray(clauses) && clauses.length) {
    return clauses
      .filter(c => Array.isArray(c) && c.length)
      .map(c => ({
        key: c.join('|'),
        names: c.map(nameOf),
        coef: Number(feats[c[0]] ?? feats[String(c[0])]) || 0,
      }))
  }
  return Object.entries(feats)
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([idx, coef]) => ({ key: String(idx), names: [nameOf(idx)], coef: Number(coef) || 0 }))
}

/** "A ∨ B" for a clause, "A" for a single feature. */
export function termLabel(term, labelOf = n => n) {
  return term.names.map(labelOf).join(` ${OR_SIGN} `)
}

/** "+1", "-1", "+2"... */
export function coefLabel(coef) {
  const c = Number(coef) || 0
  return c > 0 ? `+${c}` : String(c)
}

/** 'binary', 'ternary', 'pow2' or 'ratio' for a language name or alias, OR variants included. */
export function languageFamily(language) {
  const key = String(language || '').trim().toLowerCase().replace(/[-_]or$/, '')
  return {
    bin: 'binary', binary: 'binary', '0': 'binary',
    ter: 'ternary', ternary: 'ternary', '1': 'ternary',
    pow2: 'pow2', '2': 'pow2',
    ratio: 'ratio', '3': 'ratio',
  }[key] || 'ternary'
}

/**
 * Readable formula from a list of terms, e.g. "((A ∨ B) + C) - (D)" or
 * "(A + B) / (C + ε)". A prevalence model marks its features with ⁰, a log
 * model wraps them in ln(), Pow2 coefficients are written "2*A".
 */
export function formatFormulaFromTerms(terms, { language, dataType, labelOf } = {}) {
  if (!terms || !terms.length) return ''
  const dt = String(dataType || 'raw').toLowerCase()
  const label = labelOf || (n => n)
  const family = languageFamily(language)
  const mark = n => (dt === 'prev' || dt === 'prevalence') ? `${label(n)}⁰` : dt === 'log' ? `ln(${label(n)})` : label(n)
  const text = t => {
    const names = t.names.map(mark)
    const body = names.length > 1 ? `(${names.join(` ${OR_SIGN} `)})` : names[0]
    return family === 'pow2' && Math.abs(t.coef) !== 1 ? `${Math.abs(t.coef)}*${body}` : body
  }
  // a side with several terms is parenthesised; a lone term is not
  const side = parts => (parts.length === 1 ? parts[0] : `(${parts.join(' + ')})`)
  const pos = terms.filter(t => t.coef > 0).map(text)
  const neg = terms.filter(t => t.coef < 0).map(text)
  const posStr = pos.length ? side(pos) : '0'
  if (family === 'ratio') return `${posStr} / ${side([...neg, 'ε'])}`
  if (neg.length) return `${posStr} - ${side(neg)}`
  return pos.length ? pos.join(' + ') : '0'
}

/**
 * Readable formula of a model from the results JSON (see `modelTerms`).
 * `language` and `dataType` default to the model's metrics.
 */
export function formatModelFormula(model, { language, dataType, labelOf } = {}) {
  const terms = modelTerms(model)
  if (!terms.length) return ''
  return formatFormulaFromTerms(terms, {
    language: language ?? model.metrics?.language ?? model.language ?? '',
    dataType: dataType ?? model.metrics?.data_type ?? model.data_type ?? 'raw',
    labelOf,
  })
}

export { isOrLanguage }
