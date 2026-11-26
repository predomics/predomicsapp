/**
 * WCAG contrast of the theme's text colours against every surface they sit on,
 * read from the CSS variables in src/App.vue (light and dark).
 *
 *   node tools/contrast.mjs     report; exit 1 if a pair is below 4.5:1   (npm run check:contrast)
 *
 * The same check runs in the unit tests (src/__tests__/quality.test.js).
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

export const MIN_RATIO = 4.5

function luminance(hex) {
  const h = hex.replace('#', '')
  const [r, g, b] = [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16) / 255)
  const f = c => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
}

export function contrastRatio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

function tokens(block) {
  const out = {}
  for (const m of block.matchAll(/--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) out[m[1]] = m[2].toLowerCase()
  return out
}

const SURFACES = ['bg-page', 'bg-card', 'bg-card-hover', 'bg-input', 'bg-badge', 'bg-tab-switcher']
/** [text token, surfaces it is used on] */
export const PAIRS = [
  ...['text-primary', 'text-body', 'text-secondary', 'text-muted', 'text-faint'].map(t => [t, SURFACES]),
  ['success-dark', ['success-bg', 'bg-card']],
  ['warning-dark', ['warning-bg', 'bg-card']],
  ['danger-dark', ['danger-bg', 'bg-card']],
  ['danger', ['bg-card', 'bg-page', 'danger-bg']],
  ['accent', ['bg-card', 'bg-page', 'bg-input']],
  ['info', ['info-bg', 'bg-card']],
  ['text-nav-link', ['bg-navbar']],
  ['accent-text', ['accent']],
]

/** [{ theme, token, color, worst }] for every checked text token. */
export function checkContrast(appVueSource) {
  const light = tokens(/:root\s*\{([\s\S]*?)\n\}/.exec(appVueSource)[1])
  const dark = tokens(/:root\.dark\s*\{([\s\S]*?)\n\}/.exec(appVueSource)[1])
  const rows = []
  for (const [theme, vars] of [['light', light], ['dark', dark]]) {
    for (const [token, surfaces] of PAIRS) {
      if (!vars[token]) continue
      const worst = Math.min(...surfaces.filter(s => vars[s]).map(s => contrastRatio(vars[token], vars[s])))
      rows.push({ theme, token, color: vars[token], worst })
    }
  }
  return rows
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const rows = checkContrast(readFileSync('src/App.vue', 'utf8'))
  let bad = 0
  for (const r of rows) {
    const fail = r.worst < MIN_RATIO
    if (fail) bad++
    console.log(`${r.theme.padEnd(5)} --${r.token.padEnd(15)} ${r.color}  worst ${r.worst.toFixed(2)}:1${fail ? '  <-- below 4.5:1' : ''}`)
  }
  console.log(`${bad} failing pair(s)`)
  if (bad) process.exit(1)
}
