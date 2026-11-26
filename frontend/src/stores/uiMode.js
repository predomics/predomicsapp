import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const STORAGE_KEY = 'ui_mode'
const MODES = ['simple', 'expert']

/**
 * Interface mode, chosen with the Simple / Expert switch in the navbar.
 *
 *  - simple: one page per project (data → run → result), presets only, no
 *            exploration tools. For a first analysis or a non-specialist user.
 *  - expert: the full application (all tabs, parameters, charts, tools).
 *
 * The choice is remembered in this browser. Existing users keep the full
 * interface until they switch.
 */
export const useUiModeStore = defineStore('uiMode', () => {
  const stored = (() => {
    try { return localStorage.getItem(STORAGE_KEY) } catch { return null }
  })()
  const mode = ref(MODES.includes(stored) ? stored : 'expert')

  const isSimple = computed(() => mode.value === 'simple')

  function setMode(m) {
    if (!MODES.includes(m)) return
    mode.value = m
    try { localStorage.setItem(STORAGE_KEY, m) } catch { /* storage unavailable: still switches */ }
  }

  function toggle() {
    setMode(isSimple.value ? 'expert' : 'simple')
  }

  return { mode, isSimple, setMode, toggle }
})
