<template>
  <Teleport to="body">
    <div v-if="confirmState.open" class="confirm-overlay" @click.self="settle(false)">
      <div class="confirm-box" v-dialog="() => settle(false)" aria-labelledby="confirm-title" aria-describedby="confirm-msg">
        <h3 id="confirm-title">{{ confirmState.title || $t('common.confirmTitle') }}</h3>
        <p id="confirm-msg" class="confirm-msg">{{ confirmState.message }}</p>
        <div class="confirm-actions">
          <button type="button" class="btn-cancel" data-autofocus @click="settle(false)">
            {{ confirmState.cancelLabel || $t('common.cancel') }}
          </button>
          <button type="button" :class="['btn-ok', { danger: confirmState.danger }]" @click="settle(true)">
            {{ confirmState.confirmLabel || $t('common.confirm') }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { useConfirm } from '../composables/useConfirm'
import { vDialog } from '../directives/dialog'
const { confirmState, settle } = useConfirm()
</script>

<style scoped>
.confirm-overlay {
  position: fixed; inset: 0; z-index: 10000;
  background: rgba(0, 0, 0, 0.45);
  display: flex; align-items: center; justify-content: center;
  padding: 1rem;
}
.confirm-box {
  background: var(--bg-card); color: var(--text-body);
  border-radius: 10px; padding: 1.25rem 1.5rem;
  width: 100%; max-width: 440px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
}
.confirm-box h3 { font-size: 1.05rem; color: var(--text-primary); margin-bottom: 0.5rem; }
.confirm-msg { font-size: 0.9rem; line-height: 1.45; white-space: pre-line; margin-bottom: 1.1rem; }
.confirm-actions { display: flex; justify-content: flex-end; gap: 0.6rem; }
.confirm-actions button {
  padding: 0.45rem 1rem; border-radius: 6px; font-size: 0.88rem; cursor: pointer;
  border: 1px solid var(--border);
}
.btn-cancel { background: var(--bg-card); color: var(--text-body); }
.btn-ok { background: var(--accent); color: var(--accent-text); border-color: var(--accent); }
.btn-ok.danger { background: var(--danger-dark); border-color: var(--danger-dark); color: #fff; }
</style>
