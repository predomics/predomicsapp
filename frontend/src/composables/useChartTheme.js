/**
 * Shared Plotly chart theming composable.
 * Provides dark/light color palette and a default layout builder
 * so every chart across DataTab and ResultsTab looks consistent.
 */
import { useThemeStore } from '../stores/theme'

export function useChartTheme() {
  const themeStore = useThemeStore()

  function chartColors() {
    const dark = themeStore.isDark
    return {
      isDark: dark,
      // predomicspkg core palette: deepskyblue / firebrick
      class0: dark ? '#00BFFF' : '#00688B',          // deepskyblue1 / deepskyblue4
      class1: dark ? '#FF3030' : '#8B1A1A',           // firebrick1 / firebrick4
      class0Light: '#00BFFF',                          // deepskyblue1 (always)
      class1Light: '#FF3030',                          // firebrick1 (always)
      accent: dark ? '#BA55D3' : '#9932CC',            // darkorchid (from predomics quality palette)
      grid: dark ? '#3a3a52' : '#e0e0e0',
      text: dark ? '#d0d0dc' : '#2c3e50',
      paper: dark ? '#1e1e2e' : '#ffffff',
      dimmed: dark ? '#555566' : '#b0bec5',
      danger: dark ? '#FF3030' : '#8B1A1A',            // firebrick
      positive: dark ? '#00BFFF' : '#00688B',          // deepskyblue (positive coeff)
      negative: dark ? '#FF3030' : '#8B1A1A',          // firebrick (negative coeff)
      warn: dark ? '#e5c07b' : '#f57f17',
      // Transparent variants for fills and backgrounds
      class0Alpha: 'rgba(0, 191, 255, 0.35)',         // deepskyblue1 @ 35%
      class1Alpha: 'rgba(255, 48, 48, 0.35)',         // firebrick1 @ 35%
      positiveAlpha: 'rgba(0, 191, 255, 0.25)',       // deepskyblue1 @ 25%
      negativeAlpha: 'rgba(255, 48, 48, 0.25)',       // firebrick1 @ 25%
      accentAlpha: 'rgba(186, 85, 211, 0.30)',        // darkorchid @ 30%
    }
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

  /** Build a short display label: "msp_0069 P. vulgatus" */
  function featureLabel(name, annotations) {
    const ann = annotations[name]
    if (!ann?.species) return name
    const parts = ann.species.split(' ')
    if (parts.length >= 2) return `${name} ${parts[0][0]}. ${parts.slice(1).join(' ')}`
    return `${name} ${ann.species}`
  }

  /** Functional annotation properties from biobanks.gmt.bio */
  const FUNC_PROPS = [
    { key: 'butyrate',      label: 'Butyrate',      desc: { 1: 'Producer' } },
    { key: 'inflammation',  label: 'Inflammation',   desc: { 1: 'Enriched', '-1': 'Depleted' } },
    { key: 'transit',       label: 'Transit',        desc: { 1: 'Fast', '-1': 'Slow' } },
    { key: 'oralisation',   label: 'Oral origin',    desc: { 1: 'Oral' } },
  ]

  return { themeStore, chartColors, chartLayout, featureLabel, FUNC_PROPS }
}
