/**
 * Open/closed state of collapsible sections (components/CollapsibleSection.vue).
 *
 * The state a user chooses is remembered in localStorage per section id, so a
 * section folded once stays folded on the next job and the next visit. Mounted
 * sections register themselves so a page can fold or unfold all of them at once.
 */
import { reactive } from 'vue'

const STORAGE_KEY = 'predomics.sections'

function load() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

const chosen = reactive(load())        // sid -> boolean (only what the user set)
const mounted = reactive(new Map())    // sid -> { defaultOpen, resize }

function save() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(chosen)) } catch { /* storage full or disabled */ }
}

export function isSectionOpen(sid, defaultOpen = true) {
  return typeof chosen[sid] === 'boolean' ? chosen[sid] : defaultOpen
}

export function setSectionOpen(sid, open) {
  chosen[sid] = !!open
  save()
}

export function registerSection(sid, defaultOpen, resize) {
  mounted.set(sid, { defaultOpen, resize })
}

export function unregisterSection(sid) {
  mounted.delete(sid)
}

/** Sections currently on screen, with their state. */
export function mountedSections() {
  return [...mounted.entries()].map(([sid, s]) => ({ sid, open: isSectionOpen(sid, s.defaultOpen) }))
}

/** Fold or unfold every section currently on screen. */
export function setAllSections(open) {
  for (const [sid, s] of mounted.entries()) {
    const wasOpen = isSectionOpen(sid, s.defaultOpen)
    chosen[sid] = !!open
    if (open && !wasOpen) s.resize?.()
  }
  save()
}

/** Forget every choice (sections go back to their defaults). */
export function resetSections() {
  for (const key of Object.keys(chosen)) delete chosen[key]
  save()
}

export function useSections() {
  return { isSectionOpen, setSectionOpen, setAllSections, mountedSections, resetSections }
}
