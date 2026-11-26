<template>
  <div v-if="error" class="async-state async-error" role="alert">
    <span class="async-icon" aria-hidden="true">&#9888;</span>
    <div class="async-body">
      <p class="async-title">{{ errorTitle || $t('common.loadFailed') }}</p>
      <p class="async-detail">{{ error }}</p>
    </div>
    <button v-if="retry" type="button" class="async-retry" @click="retry">{{ $t('common.retry') }}</button>
  </div>
  <div v-else-if="loading" class="async-state async-loading" role="status" aria-live="polite">
    <span class="async-spinner" aria-hidden="true"></span>
    <span>{{ slow ? (slowText || $t('common.stillWorking')) : (loadingText || $t('common.loading')) }}</span>
  </div>
  <div v-else-if="empty" class="async-state async-empty">
    <slot name="empty">{{ emptyText || $t('common.noData') }}</slot>
  </div>
  <slot v-else />
</template>

<script setup>
/**
 * One place for the three states every data view has: loading (with a
 * "still working…" hint after a few seconds), error with a Retry button,
 * and empty. Renders the default slot otherwise.
 */
import { ref, watch, onUnmounted } from 'vue'

const props = defineProps({
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  empty: { type: Boolean, default: false },
  retry: { type: Function, default: null },
  loadingText: { type: String, default: '' },
  slowText: { type: String, default: '' },
  emptyText: { type: String, default: '' },
  errorTitle: { type: String, default: '' },
  slowAfterMs: { type: Number, default: 8000 },
})

const slow = ref(false)
let timer = null
watch(() => props.loading, (v) => {
  clearTimeout(timer)
  slow.value = false
  if (v) timer = setTimeout(() => { slow.value = true }, props.slowAfterMs)
}, { immediate: true })
onUnmounted(() => clearTimeout(timer))
</script>

<style scoped>
.async-state {
  display: flex; align-items: center; gap: 0.75rem;
  padding: 1rem 1.25rem; border-radius: 8px;
  font-size: 0.9rem; color: var(--text-secondary);
}
.async-loading { justify-content: center; padding: 2rem 1rem; }
.async-empty { justify-content: center; padding: 2rem 1rem; text-align: center; }
.async-error {
  background: var(--danger-bg); color: var(--danger-dark);
  border: 1px solid var(--danger); align-items: flex-start;
}
.async-icon { font-size: 1.2rem; line-height: 1.2; }
.async-body { flex: 1; min-width: 0; }
.async-title { font-weight: 600; margin-bottom: 0.15rem; }
.async-detail { font-size: 0.85rem; overflow-wrap: anywhere; }
.async-retry {
  background: var(--bg-card); color: var(--danger-dark);
  border: 1px solid var(--danger-dark); border-radius: 6px;
  padding: 0.35rem 0.9rem; font-size: 0.85rem; font-weight: 600; cursor: pointer;
  white-space: nowrap;
}
.async-spinner {
  width: 18px; height: 18px; border-radius: 50%;
  border: 2px solid var(--border); border-top-color: var(--info);
  animation: async-spin 0.8s linear infinite;
}
@keyframes async-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .async-spinner { animation-duration: 2.5s; } }
</style>
