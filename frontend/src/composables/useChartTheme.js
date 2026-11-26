/**
 * Shared Plotly chart theming composable.
 * Provides dark/light color palette and a default layout builder
 * so every chart across DataTab and ResultsTab looks consistent.
 */
import { useThemeStore } from '../stores/theme'
import { abbreviateSpecies, isLineage } from '../utils/chartLabels'
import { ct } from '../utils/chartText'

const CLASS_SYMBOLS = ['circle', 'diamond', 'square', 'cross']
const CLASS_DASHES = ['solid', 'dash', 'dot', 'dashdot']
const CLASS_PATTERNS = ['', '/', 'x', '.']

/** '#rrggbb' or 'rgb(r, g, b)' → 'rgba(r, g, b, a)'. Anything else is returned unchanged. */
export function withAlpha(color, alpha) {
  const text = String(color)
  const rgb = /^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/.exec(text)
  if (rgb) return `rgba(${rgb[1]}, ${rgb[2]}, ${rgb[3]}, ${alpha})`
  const h = text.replace('#', '')
  if (!/^[0-9a-fA-F]{6}$/.test(h)) return color
  const [r, g, b] = [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16))
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

/**
 * "+" / "−" written in the cells of a signed (-1 / 0 / +1) heatmap, so the sign
 * does not rest on colour alone. Spread into the trace: `{ z, ...signCells(z) }`.
 * Left out for very large matrices, where the marks would be illegible.
 */
export function signCells(matrix, maxCells = 1500) {
  const rows = Array.isArray(matrix) ? matrix : []
  const cells = rows.reduce((n, row) => n + (Array.isArray(row) ? row.length : 0), 0)
  if (!cells || cells > maxCells) return {}
  return {
    text: rows.map(row => row.map(v => (v > 0 ? '+' : v < 0 ? '−' : ''))),
    texttemplate: '%{text}',
    textfont: { size: 10 },
  }
}

export function useChartTheme() {
  const themeStore = useThemeStore()

  function chartColors() {
    const dark = themeStore.isDark
    // Class / sign colours are the Okabe–Ito blue and vermillion-orange: told apart
    // under the common colour-vision deficiencies, and paired everywhere with a
    // second cue (marker symbol, hatch pattern, line dash — see classStyle()).
    const class0 = dark ? '#56B4E9' : '#0072B2'
    const class1 = dark ? '#E69F00' : '#D55E00'
    const accent = dark ? '#CC79A7' : '#9B4F7C'
    const paper = dark ? '#1e1e2e' : '#ffffff'
    return {
      isDark: dark,
      class0,
      class1,
      class0Light: '#56B4E9',                          // bright variants (same in both themes)
      class1Light: '#E69F00',
      accent,
      grid: dark ? '#3a3a52' : '#e0e0e0',
      text: dark ? '#d0d0dc' : '#2c3e50',
      paper,
      transparent: 'rgba(0,0,0,0)',
      dimmed: dark ? '#7a7a8c' : '#8a979e',
      neutral: dark ? '#6b6b7d' : '#bdbdbd',           // "not significant", background series
      danger: class1,
      positive: class0,                                // positive coefficient
      negative: class1,                                // negative coefficient
      warn: dark ? '#F0E442' : '#8a6d00',
      good: dark ? '#35c9a5' : '#007a5a',              // best / first-rank marks (Okabe–Ito bluish green)
      highlight: dark ? '#F0E442' : '#b58900',         // selected / rejected / in-signature marks
      highlightAlpha: dark ? 'rgba(240, 228, 66, 0.30)' : 'rgba(181, 137, 0, 0.25)',
      edge: dark ? 'rgba(150,150,150,0.30)' : 'rgba(100,100,100,0.25)',
      edgeNegative: withAlpha(class1, 0.4),
      // Transparent variants for fills and backgrounds
      class0Alpha: withAlpha(class0, 0.35),
      class1Alpha: withAlpha(class1, 0.35),
      positiveAlpha: withAlpha(class0, 0.25),
      negativeAlpha: withAlpha(class1, 0.25),
      accentAlpha: withAlpha(accent, 0.30),
      // Categorical series (jobs, languages, modules…): Okabe–Ito order.
      series: [class0, class1, dark ? '#35c9a5' : '#009E73', accent, dark ? '#F0E442' : '#8a6d00',
        dark ? '#9ad0f5' : '#3b8fc4', dark ? '#f2b98f' : '#a34700', dark ? '#b0b0b8' : '#6b6b6b',
        dark ? '#7fe0c8' : '#00644a', dark ? '#e3a9c6' : '#7a3a60'],
      // Colour scales. Diverging: class 0 ↔ neutral ↔ class 1. Sequential: light → dark, single hue.
      diverging: [[0, class0], [0.5, dark ? '#2a2a3a' : '#f7f7f7'], [1, class1]],
      divergingSoft: [[0, withAlpha(class0, 0.55)], [0.5, paper], [1, withAlpha(class1, 0.55)]],
      sequential: [[0, paper], [1, class0]],
      sequentialWarm: dark
        ? [[0, '#1e1e2e'], [0.25, '#5c3a12'], [0.5, '#9c5a10'], [0.8, '#d98a1c'], [1, '#ffd27a']]
        : [[0, '#ffffff'], [0.2, '#fee8c8'], [0.5, '#fdbb84'], [0.8, '#e34a33'], [1, '#b30000']],
      // Density (counts): magma, light → dark on a light page and dark → light on a dark
      // one, so more models always means more contrast with the background. The ends
      // closest to the background are trimmed so a single model is still visible;
      // empty cells are not coloured at all (null), they show the background.
      scaleDensity: dark
        ? [[0, '#3b0f70'], [0.2, '#641a80'], [0.4, '#b73779'], [0.6, '#f7705c'], [0.8, '#fecf92'], [1, '#fcfdbf']]
        : [[0, '#fecf92'], [0.2, '#fe9f6d'], [0.4, '#f7705c'], [0.6, '#de4968'], [0.8, '#8c2981'], [1, '#3b0f70']],
      // Perceptually uniform, colour-blind-safe named scales for dense heatmaps.
      scaleUniform: 'Viridis',
      scaleHeat: 'Cividis',
    }
  }

  /**
   * Colour plus a non-colour cue for the i-th class (0, 1, …): use the symbol on
   * scatter markers, the pattern on bars and the dash on lines, so a chart reads
   * without colour.
   */
  function classStyle(i) {
    const c = chartColors()
    const k = Math.max(0, Number(i) || 0) % CLASS_SYMBOLS.length
    return {
      color: [c.class0, c.class1, c.accent, c.good][k],
      symbol: CLASS_SYMBOLS[k],
      dash: CLASS_DASHES[k],
      pattern: CLASS_PATTERNS[k],
    }
  }

  /** Bar marker for a signed quantity: colour plus a hatch on negatives. */
  function signMarker(value) {
    const c = chartColors()
    return value >= 0
      ? { color: c.positive }
      : { color: c.negative, pattern: { shape: '/', fgcolor: c.paper, fgopacity: 0.55, size: 6 } }
  }

  function chartLayout(overrides = {}) {
    const c = chartColors()
    return {
      margin: { t: 20, b: 50, l: 60, r: 20 },
      height: 300,
      font: { family: 'system-ui, sans-serif', size: 12, color: c.text },
      paper_bgcolor: c.paper,
      plot_bgcolor: c.paper,
      xaxis: { gridcolor: c.grid, color: c.text, ...overrides.xaxis },
      yaxis: { gridcolor: c.grid, color: c.text, ...overrides.yaxis },
      legend: { font: { color: c.text }, ...overrides.legend },
      ...overrides,
    }
  }

  /**
   * Label for a feature: "msp_0069 P. vulgatus".
   *
   * A lineage-style name ("msp_0069;Bacteria;…;Phocaeicola vulgatus") already
   * carries its species and is returned unchanged: it must stay unique because
   * charts use it as the category value. What is drawn on the axis is shortened
   * centrally (utils/chartLabels.js); for text outside charts use shortFeatureName.
   */
  function featureLabel(name, annotations) {
    if (isLineage(name)) return name
    const species = annotations?.[name]?.species
    if (!species) return name
    return `${name} ${abbreviateSpecies(species)}`
  }

  /**
   * Functional annotation properties from biobanks.gmt.bio.
   * `label` and `desc` are getters so they follow the current language.
   */
  const FUNC_PROPS = [
    { key: 'butyrate',     get label() { return ct('Butyrate') },     get desc() { return { 1: ct('Producer') } } },
    { key: 'inflammation', get label() { return ct('Inflammation') }, get desc() { return { 1: ct('Enriched'), '-1': ct('Depleted') } } },
    { key: 'transit',      get label() { return ct('Transit') },      get desc() { return { 1: ct('Fast'), '-1': ct('Slow') } } },
    { key: 'oralisation',  get label() { return ct('Oral origin') },  get desc() { return { 1: ct('Oral') } } },
  ]

  return { themeStore, chartColors, chartLayout, classStyle, signMarker, featureLabel, FUNC_PROPS }
}
