<template>
  <Teleport to="body">
    <div class="toast-container" role="region" :aria-label="$t('common.notifications')">
      <div class="toast-live" aria-live="polite" aria-atomic="false">
        <transition-group name="toast">
          <div
            v-for="t in toasts"
            :key="t.id"
            :class="['toast', t.type]"
            :role="t.type === 'error' ? 'alert' : 'status'"
          >
            <span class="toast-icon" aria-hidden="true">{{ icon(t.type) }}</span>
            <span class="toast-msg">{{ t.message }}</span>
            <button v-if="t.action" type="button" class="toast-action" @click="runAction(t)">{{ t.action.label }}</button>
            <button type="button" class="toast-close" :aria-label="$t('common.dismiss')" @click="removeToast(t.id)">&times;</button>
          </div>
        </transition-group>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { useToast } from '../composables/useToast'
const { toasts, removeToast } = useToast()

function icon(type) {
  const icons = { success: '✓', error: '✗', warning: '⚠', info: 'ℹ' }
  return icons[type] || icons.info
}

function runAction(t) {
  try { t.action.onClick?.() } finally { removeToast(t.id) }
}
</script>

<style scoped>
.toast-container {
  position: fixed;
  top: 1rem;
  right: 1rem;
  z-index: 9999;
  max-width: 400px;
  pointer-events: none;
}
.toast-live {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.toast {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 0.8rem;
  border-radius: 8px;
  font-size: 0.85rem;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  transition: all 0.3s ease;
  pointer-events: auto;
  background: var(--bg-card);
  color: var(--text-body);
  border: 1px solid var(--border-light);
  border-left-width: 4px;
}

.toast.success { background: var(--success-bg); color: var(--success-dark); border-left-color: var(--success); }
.toast.error   { background: var(--danger-bg);  color: var(--danger-dark);  border-left-color: var(--danger); }
.toast.warning { background: var(--warning-bg); color: var(--warning-dark); border-left-color: var(--warning); }
.toast.info    { background: var(--info-bg);    color: var(--info);         border-left-color: var(--info); }

.toast-icon { font-size: 1rem; flex-shrink: 0; }
.toast-msg { flex: 1; line-height: 1.3; overflow-wrap: anywhere; }
.toast-action {
  background: transparent;
  border: 1px solid currentColor;
  color: inherit;
  border-radius: 4px;
  padding: 0.15rem 0.5rem;
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.toast-close {
  background: none;
  border: none;
  font-size: 1.1rem;
  cursor: pointer;
  color: inherit;
  opacity: 0.7;
  padding: 0 0.15rem;
  line-height: 1;
}
.toast-close:hover { opacity: 1; }

.toast-enter-active { animation: slideIn 0.3s ease; }
.toast-leave-active { animation: slideOut 0.2s ease; }

@keyframes slideIn {
  from { transform: translateX(100%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}
@keyframes slideOut {
  from { transform: translateX(0); opacity: 1; }
  to { transform: translateX(100%); opacity: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .toast-enter-active, .toast-leave-active { animation: none; }
}
</style>
