/**
 * Promise-based confirmation dialog (replaces window.confirm).
 *
 *   const { confirmDialog } = useConfirm()
 *   if (!(await confirmDialog({ message: 'Delete?', danger: true }))) return
 *
 * A plain string is accepted as the message. Rendered by <ConfirmDialog/>
 * mounted once in App.vue.
 */
import { reactive } from 'vue'

const state = reactive({
  open: false,
  title: '',
  message: '',
  confirmLabel: '',
  cancelLabel: '',
  danger: false,
  _resolve: null,
})

function confirmDialog(opts) {
  const o = typeof opts === 'string' ? { message: opts } : (opts || {})
  if (state.open && state._resolve) state._resolve(false)
  return new Promise((resolve) => {
    state.title = o.title || ''
    state.message = o.message || ''
    state.confirmLabel = o.confirmLabel || ''
    state.cancelLabel = o.cancelLabel || ''
    state.danger = !!o.danger
    state._resolve = resolve
    state.open = true
  })
}

function settle(value) {
  const r = state._resolve
  state.open = false
  state._resolve = null
  if (r) r(value)
}

export function useConfirm() {
  return { confirmState: state, confirmDialog, settle }
}
