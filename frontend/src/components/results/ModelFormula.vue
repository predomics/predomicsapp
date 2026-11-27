<template>
  <section class="model-rule" v-if="terms.length">
    <div class="rule-header">
      <h3>{{ $t('results.modelRule') }}</h3>
      <span class="rule-meta">{{ metaText }}</span>
    </div>

    <!-- Visual form of the rule: positive terms, operator, negative terms, decision -->
    <div class="rule-visual" :class="{ ratio: family === 'ratio' }">
      <div class="rule-side positive">
        <div class="side-label">{{ $t('results.positiveTerms') }}</div>
        <div class="side-chips">
          <span v-for="term in positive" :key="term.key" class="rule-chip positive" :class="{ clause: term.names.length > 1 }" :title="term.names.join(' ∨ ')">
            <span v-if="family === 'pow2' && Math.abs(term.coef) !== 1" class="weight">{{ Math.abs(term.coef) }}×</span>
            <template v-for="(name, i) in term.names" :key="name">
              <span v-if="i > 0" class="or-sign" aria-label="or">{{ ' ∨ ' }}</span>
              <span>{{ shortName(labelOf(name)) }}</span>
            </template>
          </span>
          <span v-if="!positive.length" class="rule-none">{{ $t('results.noTerms') }}</span>
        </div>
      </div>

      <template v-if="family !== 'binary' || negative.length">
        <div class="rule-op" :aria-label="family === 'ratio' ? 'divided by' : 'minus'">{{ family === 'ratio' ? '÷' : '−' }}</div>
        <div class="rule-side negative">
          <div class="side-label">{{ $t('results.negativeTerms') }}</div>
          <div class="side-chips">
            <span v-for="term in negative" :key="term.key" class="rule-chip negative" :class="{ clause: term.names.length > 1 }" :title="term.names.join(' ∨ ')">
              <span v-if="family === 'pow2' && Math.abs(term.coef) !== 1" class="weight">{{ Math.abs(term.coef) }}×</span>
              <template v-for="(name, i) in term.names" :key="name">
                <span v-if="i > 0" class="or-sign" aria-label="or">{{ ' ∨ ' }}</span>
                <span>{{ shortName(labelOf(name)) }}</span>
              </template>
            </span>
            <span v-if="family === 'ratio'" class="rule-chip epsilon" :title="$t('results.epsilonHint')">ε</span>
            <span v-if="!negative.length && family !== 'ratio'" class="rule-none">{{ $t('results.noTerms') }}</span>
          </div>
        </div>
      </template>
    </div>

    <p class="rule-decision" v-if="!isRegression && threshold !== null">
      <span class="decision-badge positive-class">{{ classNameFor(1) }}</span>
      {{ $t('results.decisionWhen') }} <strong>{{ $t('results.scoreWord') }} ≥ {{ thresholdText }}</strong>,
      {{ $t('results.decisionOtherwise') }} <span class="decision-badge negative-class">{{ classNameFor(0) }}</span>
    </p>

    <!-- Exact formula, with the real feature names, ready to copy -->
    <div class="rule-formula">
      <span class="formula-label">{{ $t('results.formulaLabel') }}</span>
      <code class="formula-text">{{ formulaText }}</code>
      <button type="button" class="copy-btn" @click="copyFormula">{{ copied ? $t('results.copied') : $t('results.copy') }}</button>
    </div>

    <ul class="rule-legend">
      <li>{{ scoreLegend }}</li>
      <li v-if="dataTypeHint">{{ dataTypeHint }}</li>
      <li v-if="hasClause">{{ $t('results.orClauseHint') }}</li>
    </ul>
  </section>
</template>

<script setup>
/**
 * The best model written out as a rule: its positive and negative terms as
 * chips, the decision threshold, the exact formula (copiable) and a short
 * legend explaining the score. Works for every language, classic or OR
 * (clauses "A ∨ B"), and every data type.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { shortFeatureName as shortName } from '../../utils/chartLabels'
import { termsFromIndices, formatFormulaFromTerms, languageFamily } from '../../utils/modelTerms'

const props = defineProps({
  /** best_individual of the job detail: features (index -> coef), clauses, language, data_type, threshold. */
  model: { type: Object, required: true },
  /** Feature names of the job, indexed like `model.features`. */
  featureNames: { type: Array, default: () => [] },
  /** Optional display label for a feature name (e.g. MSP annotation). */
  labelOf: { type: Function, default: n => n },
  /** Name of a class for the decision line. */
  classNameFor: { type: Function, default: c => `Class ${c}` },
  isRegression: { type: Boolean, default: false },
})

const { t } = useI18n()

const terms = computed(() => termsFromIndices(props.model?.features, props.model?.clauses, props.featureNames))
const positive = computed(() => terms.value.filter(t => t.coef > 0))
const negative = computed(() => terms.value.filter(t => t.coef < 0))
const hasClause = computed(() => terms.value.some(t => t.names.length > 1))
const family = computed(() => languageFamily(props.model?.language))
const dataType = computed(() => String(props.model?.data_type || 'raw').toLowerCase())
const threshold = computed(() => {
  const v = Number(props.model?.threshold)
  return Number.isFinite(v) ? v : null
})
const thresholdText = computed(() => (threshold.value === null ? '' : Number(threshold.value.toPrecision(4)).toString()))

const formulaText = computed(() => {
  const f = formatFormulaFromTerms(terms.value, { language: props.model?.language, dataType: dataType.value })
  return !props.isRegression && threshold.value !== null ? `${f} ≥ ${thresholdText.value}` : f
})

const metaText = computed(() => {
  const k = Object.keys(props.model?.features || {}).length
  const params = { language: props.model?.language || '', dataType: props.model?.data_type || '', k, terms: terms.value.length }
  return hasClause.value ? t('results.modelRuleMetaOr', params) : t('results.modelRuleMeta', params)
})

const scoreLegend = computed(() => {
  if (family.value === 'binary') {
    const dt = dataType.value
    return (dt === 'prev' || dt === 'prevalence') ? t('results.scoreLegendBinaryPrev') : t('results.scoreLegendBinary')
  }
  if (family.value === 'pow2') return t('results.scoreLegendPow2')
  if (family.value === 'ratio') return t('results.scoreLegendRatio')
  return t('results.scoreLegendTernary')
})

const dataTypeHint = computed(() => {
  const dt = dataType.value
  if (dt === 'prev' || dt === 'prevalence') return t('results.dataTypeHintPrev')
  if (dt === 'log') return t('results.dataTypeHintLog')
  if (dt === 'zscore') return t('results.dataTypeHintZscore')
  return t('results.dataTypeHintRaw')
})

const copied = ref(false)
function copyFormula() {
  if (!navigator.clipboard) return
  navigator.clipboard.writeText(formulaText.value).then(() => {
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  })
}
</script>

<style scoped>
.model-rule {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-left: 4px solid var(--tab-active);
  border-radius: var(--card-radius);
  padding: 1rem 1.25rem;
  margin-bottom: 1.25rem;
}
.rule-header { display: flex; align-items: baseline; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 0.75rem; }
.rule-header h3 { margin: 0; }
.rule-meta { color: var(--text-secondary); font-size: 0.85rem; }

.rule-visual {
  display: flex;
  align-items: stretch;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.rule-side {
  flex: 1 1 240px;
  border-radius: 8px;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--border-light);
}
.rule-side.positive { background: var(--success-bg-alt); }
.rule-side.negative { background: var(--danger-bg); background-blend-mode: lighten; }
.side-label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-secondary); margin-bottom: 0.4rem; }
.side-chips { display: flex; flex-wrap: wrap; gap: 0.45rem; align-items: center; }
.rule-chip {
  display: inline-flex;
  align-items: center;
  padding: 0.4rem 0.8rem;
  border-radius: 20px;
  font-size: 0.95rem;
  font-weight: 600;
  background: var(--bg-card);
  border: 1px solid transparent;
}
.rule-chip.positive { color: var(--success-dark); border-color: var(--success); }
.rule-chip.negative { color: var(--danger-dark); border-color: var(--danger); }
.rule-chip.clause { border-style: dashed; }
.rule-chip.epsilon { color: var(--text-secondary); border-color: var(--border); font-style: italic; }
.rule-chip .weight { opacity: 0.75; margin-right: 0.25rem; font-weight: 500; }
.or-sign { white-space: pre; opacity: 0.65; font-weight: 400; }
.rule-none { color: var(--text-muted); font-style: italic; font-size: 0.9rem; }
.rule-op {
  align-self: center;
  font-size: 1.8rem;
  font-weight: 300;
  color: var(--text-primary);
  padding: 0 0.25rem;
}
/* A ratio reads as a fraction: numerator above the denominator */
.rule-visual.ratio { flex-direction: column; gap: 0.25rem; }
.rule-visual.ratio .rule-op { align-self: stretch; text-align: center; font-size: 1.1rem; border-top: 2px solid var(--text-primary); line-height: 1.6; }

.rule-decision { margin: 0.9rem 0 0.5rem; font-size: 0.95rem; color: var(--text-body); }
.decision-badge { display: inline-block; padding: 0.15rem 0.6rem; border-radius: 12px; font-weight: 600; font-size: 0.85rem; }
.decision-badge.positive-class { background: var(--info-bg); color: var(--info); }
.decision-badge.negative-class { background: var(--bg-badge); color: var(--text-secondary); border: 1px solid var(--border-light); }

.rule-formula {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-top: 0.75rem;
  padding: 0.6rem 0.75rem;
  background: var(--bg-page);
  border-radius: 8px;
}
.formula-label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-secondary); }
.formula-text {
  flex: 1 1 300px;
  font-size: 0.95rem;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  background: transparent;
  color: var(--text-primary);
}
.copy-btn {
  padding: 0.3rem 0.7rem;
  border-radius: 6px;
  font-size: 0.78rem;
  cursor: pointer;
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-secondary);
}
.copy-btn:hover { border-color: var(--tab-active); color: var(--tab-active); }
.rule-legend { margin: 0.6rem 0 0; padding-left: 1.1rem; color: var(--text-secondary); font-size: 0.82rem; line-height: 1.45; }
.rule-legend li { margin: 0.1rem 0; }
</style>
