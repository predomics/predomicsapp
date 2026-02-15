<template>
  <svg :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`" class="progress-circle">
    <!-- Background circle -->
    <circle
      :cx="center" :cy="center" :r="radius"
      fill="none"
      :stroke="bgColor"
      :stroke-width="strokeWidth"
    />
    <!-- Progress arc -->
    <circle
      :cx="center" :cy="center" :r="radius"
      fill="none"
      :stroke="color"
      :stroke-width="strokeWidth"
      :stroke-dasharray="circumference"
      :stroke-dashoffset="dashOffset"
      stroke-linecap="round"
      class="progress-arc"
    />
    <!-- Center text -->
    <text
      :x="center" :y="center"
      text-anchor="middle"
      dominant-baseline="central"
      :font-size="fontSize"
      :fill="textColor"
      font-weight="600"
    >
      {{ label || Math.round(pct) + '%' }}
    </text>
  </svg>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  pct: { type: Number, default: 0 },
  size: { type: Number, default: 36 },
  strokeWidth: { type: Number, default: 3 },
  color: { type: String, default: '#00BFFF' },
  bgColor: { type: String, default: 'rgba(255,255,255,0.1)' },
  textColor: { type: String, default: '#dcdfe4' },
  label: { type: String, default: '' },
})

const center = computed(() => props.size / 2)
const radius = computed(() => (props.size - props.strokeWidth) / 2)
const circumference = computed(() => 2 * Math.PI * radius.value)
const dashOffset = computed(() => {
  const clampedPct = Math.min(100, Math.max(0, props.pct))
  return circumference.value * (1 - clampedPct / 100)
})
const fontSize = computed(() => Math.max(8, props.size * 0.28))
</script>

<style scoped>
.progress-circle {
  transform: rotate(-90deg);
  flex-shrink: 0;
}
.progress-arc {
  transition: stroke-dashoffset 0.4s ease;
}
/* Rotate text back so it's readable */
.progress-circle text {
  transform: rotate(90deg);
  transform-origin: center;
}
</style>
