<template>
  <div class="feature-list">
    <div
      v-for="term in terms"
      :key="term.key"
      class="feature-chip"
      :class="{ positive: term.coef > 0, negative: term.coef < 0, clause: term.names.length > 1 }"
      :title="term.names.join(' ∨ ')"
    >
      <template v-for="(name, i) in term.names" :key="name">
        <span v-if="i > 0" class="or-sign" aria-label="or">{{ ' \u2228 ' }}</span>
        <span>{{ shortName(labelOf(name)) }}</span>
      </template>
      <span v-if="showCoef" class="coef"> ({{ coefLabel(term.coef) }})</span>
    </div>
  </div>
</template>

<script setup>
/**
 * The terms of one model as chips: one chip per feature for a classic model, one
 * chip per clause ("A ∨ B") for a model of an OR language. The coefficient shown
 * is the real one (+1, -1, +2...).
 */
import { computed } from 'vue'
import { shortFeatureName as shortName } from '../../utils/chartLabels'
import { modelTerms, coefLabel } from '../../utils/modelTerms'

const props = defineProps({
  /** Population entry or basket item: named_features and, for OR models, named_clauses. */
  model: { type: Object, required: true },
  /** Optional display label for a feature name (e.g. MSP annotation). */
  labelOf: { type: Function, default: n => n },
  showCoef: { type: Boolean, default: true },
})

const terms = computed(() => modelTerms(props.model))
</script>

<style scoped>
.feature-list { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.feature-chip {
  padding: 0.35rem 0.75rem;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 500;
}
.feature-chip.positive { background: var(--success-bg); color: var(--success-dark); }
.feature-chip.negative { background: var(--danger-bg); color: var(--danger-dark); }
.feature-chip.clause { border: 1px dashed currentColor; }
.or-sign { white-space: pre; opacity: 0.7; }
.coef { opacity: 0.85; }
</style>
