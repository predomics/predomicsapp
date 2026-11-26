/**
 * Toast notification composable — global reactive toast queue.
 *
 * Usage:
 *   import { useToast } from '../composables/useToast'
 *   const { addToast } = useToast()
 *   addToast('Saved', 'success')                 // success | error | warning | info
 *   addToast('Job done', 'success', 8000, { action: { label: 'View results', onClick } })
 */
import { reactive } from 'vue'

const toasts = reactive([])
let _nextId = 0

function addToast(message, type = 'info', duration = 5000, options = {}) {
  // Collapse identical messages that are already on screen.
  const dup = toasts.find((t) => t.message === message && t.type === type)
  if (dup) return dup.id
  const id = _nextId++
  toasts.push({ id, message, type, action: options.action || null })
  if (duration > 0) {
    setTimeout(() => removeToast(id), duration)
  }
  return id
}

function removeToast(id) {
  const idx = toasts.findIndex((t) => t.id === id)
  if (idx >= 0) toasts.splice(idx, 1)
}

const toast = {
  success: (m, d, o) => addToast(m, 'success', d ?? 5000, o),
  error: (m, d, o) => addToast(m, 'error', d ?? 8000, o),
  warning: (m, d, o) => addToast(m, 'warning', d ?? 6000, o),
  info: (m, d, o) => addToast(m, 'info', d ?? 5000, o),
}

export function useToast() {
  return { toasts, addToast, removeToast, toast }
}
