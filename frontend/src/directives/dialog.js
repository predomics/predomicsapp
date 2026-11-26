/**
 * v-dialog — shared modal behaviour for any overlay panel.
 *
 *   <div class="modal" v-dialog="close" aria-labelledby="my-title">…</div>
 *
 * Adds role="dialog" + aria-modal, moves focus inside on open, keeps Tab
 * inside the panel, closes on Escape and gives focus back to the element
 * that opened it.
 */
const FOCUSABLE = [
  'a[href]', 'button:not([disabled])', 'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])', 'textarea:not([disabled])', '[tabindex]:not([tabindex="-1"])',
].join(',')

function focusables(el) {
  return Array.from(el.querySelectorAll(FOCUSABLE)).filter(
    (n) => !n.hasAttribute('hidden') && n.getAttribute('aria-hidden') !== 'true',
  )
}

export const vDialog = {
  mounted(el, binding) {
    el.setAttribute('role', el.getAttribute('role') || 'dialog')
    el.setAttribute('aria-modal', 'true')
    if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '-1')
    el._dialogClose = binding.value
    el._dialogPrev = typeof document !== 'undefined' ? document.activeElement : null

    el._dialogKeydown = (ev) => {
      if (ev.key === 'Escape') {
        ev.stopPropagation()
        if (typeof el._dialogClose === 'function') el._dialogClose()
        return
      }
      if (ev.key !== 'Tab') return
      const items = focusables(el)
      if (items.length === 0) {
        ev.preventDefault()
        el.focus()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      const active = document.activeElement
      if (ev.shiftKey && (active === first || active === el)) {
        ev.preventDefault()
        last.focus()
      } else if (!ev.shiftKey && active === last) {
        ev.preventDefault()
        first.focus()
      }
    }
    el.addEventListener('keydown', el._dialogKeydown)

    const initial = el.querySelector('[autofocus], [data-autofocus]') || focusables(el)[0] || el
    try { initial.focus({ preventScroll: true }) } catch { /* not focusable in this env */ }
  },
  updated(el, binding) {
    el._dialogClose = binding.value
  },
  unmounted(el) {
    el.removeEventListener('keydown', el._dialogKeydown)
    const prev = el._dialogPrev
    if (prev && typeof prev.focus === 'function' && document.contains(prev)) {
      try { prev.focus({ preventScroll: true }) } catch { /* ignore */ }
    }
  },
}

export default vDialog
