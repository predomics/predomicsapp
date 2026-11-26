import { describe, it, expect, vi } from 'vitest'
import {
  shortFeatureName, ellipsize, abbreviateSpecies, isLineage, fitLongLabels, withFittedLabels, MAX_LABEL_CHARS,
  fitChartHeight, maxChartHeight, mergeLineTraces,
} from '../utils/chartLabels'

const MSP = 'msp_0001;Eukaryota;Heterokonta;Blastocystae;Blastocystida;Blastocystidae;Blastocystis;Blastocystis sp. subtype 3'
const MSP2 = 'msp_0074;Bacteria;Bacillota_A;Clostridia;Lachnospirales;Lachnospiraceae;Lachnospiraceae COE1;Lachnospiraceae COE1 sp001916965'
const MPA = 'k__Bacteria|p__Firmicutes|c__Clostridia|o__Clostridiales|f__Ruminococcaceae|g__Faecalibacterium|s__Faecalibacterium_prausnitzii'

describe('shortFeatureName', () => {
  it('keeps the id and the abbreviated species of a lineage', () => {
    expect(shortFeatureName(MSP)).toBe('msp_0001 B. sp. subtype 3')
    expect(shortFeatureName(MPA)).toBe('F. prausnitzii')
  })
  it('never exceeds the limit', () => {
    for (const n of [MSP, MSP2, MPA, 'x'.repeat(300), 'a very long free text feature name without any separator at all']) {
      expect(shortFeatureName(n).length).toBeLessThanOrEqual(MAX_LABEL_CHARS)
    }
  })
  it('leaves short names and non-strings alone', () => {
    expect(shortFeatureName('msp_0069')).toBe('msp_0069')
    expect(shortFeatureName('Age')).toBe('Age')
    expect(shortFeatureName(42)).toBe(42)
  })
  it('ellipsizes in the middle, keeping both ends', () => {
    const out = ellipsize('abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJ', 20)
    expect(out.length).toBe(20)
    expect(out.startsWith('abcdefghijkl')).toBe(true)
    expect(out.endsWith('DEFGHIJ')).toBe(true)
    expect(out).toContain('…')
  })
  it('helpers', () => {
    expect(abbreviateSpecies('Phocaeicola vulgatus')).toBe('P. vulgatus')
    expect(abbreviateSpecies('sp001916965')).toBe('sp001916965')
    expect(isLineage(MSP)).toBe(true)
    expect(isLineage('msp_0069')).toBe(false)
  })
})

describe('fitLongLabels', () => {
  it('shortens category tick text but keeps the full names as values', () => {
    const data = [{ type: 'bar', orientation: 'h', x: [1, 2], y: [MSP, MSP2] }]
    const layout = { margin: { l: 200 }, yaxis: { automargin: true } }
    const [d, l] = fitLongLabels(data, layout)
    expect(d[0].y).toEqual([MSP, MSP2]) // data untouched: hover and uniqueness preserved
    expect(l.yaxis.tickvals).toEqual([MSP, MSP2])
    expect(l.yaxis.ticktext).toEqual(['msp_0001 B. sp. subtype 3', shortFeatureName(MSP2)])
    expect(l.yaxis.automargin).toBe(true)
    expect(layout.yaxis.ticktext).toBeUndefined() // input not mutated
    expect(l.xaxis).toBeUndefined() // numeric axis untouched
  })
  it('handles both axes of a heatmap and secondary axes', () => {
    const [, l] = fitLongLabels([
      { type: 'heatmap', x: [MSP, MSP2], y: [MSP, MSP2], z: [[1, 0], [0, 1]] },
      { type: 'bar', x: [MSP], y: [3], xaxis: 'x2', yaxis: 'y2' },
    ], {})
    expect(l.xaxis.ticktext[0]).toBe('msp_0001 B. sp. subtype 3')
    expect(l.yaxis.ticktext).toHaveLength(2)
    expect(l.xaxis2.tickvals).toEqual([MSP])
    expect(l.yaxis2).toBeUndefined()
  })
  it('does nothing for short labels, numbers and dates', () => {
    const layout = { title: 't' }
    const [d, l] = fitLongLabels([{ x: ['a', 'b'], y: [1, 2] }, { x: ['2026-01-01', '2026-01-02'], y: [1, 2] }], layout)
    expect(l).toEqual(layout)
    expect(d[0].x).toEqual(['a', 'b'])
  })
  it('shortens caller-provided tick text and long legend names', () => {
    const [d, l] = fitLongLabels(
      [{ x: [0, 1], y: [1, 2], name: MSP }],
      { yaxis: { tickvals: [0, 1], ticktext: [MSP, 'short'] } },
    )
    expect(d[0].name).toBe('msp_0001 B. sp. subtype 3')
    expect(l.yaxis.tickvals).toEqual([0, 1])
    expect(l.yaxis.ticktext).toEqual(['msp_0001 B. sp. subtype 3', 'short'])
  })
  it('shortens text drawn on the plot and keeps the full text for hover', () => {
    const [d] = fitLongLabels([{ type: 'scatter', mode: 'markers+text', x: [0, 1], y: [0, 1], text: [MSP, 'short'] }], {})
    expect(d[0].text).toEqual([MSP, 'short']) // hover (%{text}) still gets the full name
    expect(d[0].texttemplate).toEqual(['msp_0001 B. sp. subtype 3', 'short'])
    const own = [{ mode: 'markers+text', x: [0], y: [0], text: [MSP], texttemplate: '%{text}' }]
    expect(fitLongLabels(own, {})[0][0].texttemplate).toBe('%{text}') // caller's choice wins
    const hoverOnly = [{ mode: 'markers', x: [0], y: [0], text: [MSP] }]
    expect(fitLongLabels(hoverOnly, {})[0][0].texttemplate).toBeUndefined()
  })
  it('labels only the largest points of a crowded plot', () => {
    const n = 179
    const text = Array.from({ length: n }, (_, i) => `node${i}`)
    const size = text.map((_, i) => 10 + i) // the last ones are the biggest
    const [d] = fitLongLabels([{ mode: 'markers+text', x: text.map(() => 0), y: text.map(() => 0), text, marker: { size } }], {})
    const drawn = d[0].texttemplate.filter(Boolean)
    expect(drawn).toHaveLength(30)
    expect(d[0].texttemplate[n - 1]).toBe('node178')
    expect(d[0].texttemplate[0]).toBe('')
    expect(d[0].text).toHaveLength(n)
    // a chart that already labels only a chosen few among many points is left alone
    const chosen = Array.from({ length: 500 }, (_, i) => (i % 50 === 0 ? `hit${i}` : ''))
    expect(fitLongLabels([{ mode: 'markers+text', x: chosen.map(() => 0), y: chosen.map(() => 0), text: chosen }], {})[0][0].texttemplate).toBeUndefined()
    const sparse = [{ mode: 'markers+text', x: [0], y: [0], text: ['a'] }]
    expect(fitLongLabels(sparse, {})[0][0].texttemplate).toBeUndefined()
  })
  it('thins very long category axes instead of drawing every tick', () => {
    const names = Array.from({ length: 500 }, (_, i) => `msp_${String(i).padStart(4, '0')};Bacteria;A;B;C;D;Genus;Genus species number ${i}`)
    const [, l] = fitLongLabels([{ x: names, y: names.map(() => 1) }], {})
    expect(l.xaxis.tickvals.length).toBeLessThanOrEqual(80)
    expect(l.xaxis.tickvals.length).toBe(l.xaxis.ticktext.length)
  })
  it('leaves non-category axes and odd input alone', () => {
    const [, l] = fitLongLabels([{ x: [MSP], y: [1] }], { xaxis: { type: 'linear' } })
    expect(l.xaxis.ticktext).toBeUndefined()
    expect(fitLongLabels(undefined, undefined)).toEqual([undefined, undefined])
  })
})

describe('withFittedLabels', () => {
  it('pre-processes newPlot and react and passes everything else through', () => {
    const lib = { newPlot: vi.fn(), react: vi.fn(), purge: vi.fn(), version: '3' }
    const P = withFittedLabels(lib)
    P.newPlot('el', [{ x: [1], y: [MSP] }], {}, { responsive: true })
    const [el, , layout, config] = lib.newPlot.mock.calls[0]
    expect(el).toBe('el')
    expect(layout.yaxis.ticktext).toEqual(['msp_0001 B. sp. subtype 3'])
    expect(config).toEqual({ responsive: true })
    P.react('el', [{ x: [MSP], y: [1] }], {})
    expect(lib.react.mock.calls[0][2].xaxis.ticktext).toHaveLength(1)
    P.purge('el')
    expect(lib.purge).toHaveBeenCalledWith('el')
    expect(P.version).toBe('3')
  })
})

describe('fitChartHeight', () => {
  const VH = 900 // -> max 720
  const names = n => Array.from({ length: n }, (_, i) => `f${i}_name`)
  const bar = n => [{ type: 'bar', orientation: 'h', x: names(n).map(() => 1), y: names(n) }]

  it('uses most of the window, within bounds', () => {
    expect(maxChartHeight(900)).toBe(720)
    expect(maxChartHeight(400)).toBe(420)
    expect(maxChartHeight(2000)).toBe(900)
  })
  it('leaves charts that already fit alone', () => {
    const layout = { height: 500 }
    expect(fitChartHeight(bar(10), layout, VH)).toEqual({ layout, scrollHeight: null })
    expect(fitChartHeight(bar(10), {}, VH).layout).toEqual({})
  })
  it('compresses a 50-row chart to the window instead of 1100 px', () => {
    const { layout, scrollHeight } = fitChartHeight(bar(50), { height: 1100 }, VH)
    expect(layout.height).toBe(720)
    expect(scrollHeight).toBeNull()
    expect(layout.yaxis.tickfont.size).toBe(10)
  })
  it('counts rows drawn at numeric positions with tick text', () => {
    const n = 50
    const data = [{ type: 'scatter', mode: 'markers', x: names(n).map(() => 1), y: names(n).map((_, i) => i) }]
    const { layout } = fitChartHeight(data, { height: 1100, yaxis: { tickvals: names(n).map((_, i) => i), ticktext: names(n), tickfont: { size: 12 } } }, VH)
    expect(layout.height).toBe(720)
    expect(layout.yaxis.tickfont.size).toBe(10)
  })
  it('scrolls a long readable list instead of stretching the page', () => {
    const { layout, scrollHeight } = fitChartHeight(bar(179), { height: 4018 }, VH)
    expect(scrollHeight).toBe(720)
    expect(layout.height).toBe(179 * 16 + 110)
    expect(layout.height).toBeLessThan(4018)
    expect(layout.yaxis.tickvals).toHaveLength(179) // every row labelled inside the scroll box
    expect(layout.xaxis?.side).toBeUndefined()
  })
  it('turns a 734-row heatmap into an overview with thinned labels', () => {
    const y = names(734)
    const { layout, scrollHeight } = fitChartHeight(
      [{ type: 'heatmap', x: ['a', 'b'], y, z: y.map(() => [0, 1]) }], { height: 10376 }, VH)
    expect(layout.height).toBe(720)
    expect(scrollHeight).toBeNull()
    expect(layout.yaxis.nticks).toBeLessThanOrEqual(51)
  })
  it('fits a mid-sized heatmap instead of scrolling it', () => {
    const labels = names(60)
    const { layout, scrollHeight } = fitChartHeight(
      [{ type: 'heatmap', x: labels, y: labels, z: labels.map(() => labels.map(() => 1)) }],
      { height: 1800, width: 1800, margin: { t: 20, b: 120, l: 200, r: 60 } }, VH, 1328)
    expect(scrollHeight).toBeNull()
    expect(layout.height).toBe(720)
    expect(layout.width).toBe(880)
  })
  it('never lets a chart be wider than its container', () => {
    const labels = names(179)
    const { layout } = fitChartHeight(
      [{ type: 'heatmap', x: labels, y: labels, z: labels.map(() => labels.map(() => 1)) }],
      { height: 5132, width: 5132, margin: { t: 20, b: 120, l: 200, r: 60 } }, VH, 1328)
    expect(layout.height).toBe(720)
    expect(layout.width).toBe(880) // stays roughly square
    expect(layout.xaxis.nticks).toBeLessThanOrEqual(45)
    const wide = fitChartHeight([{ type: 'bar', x: [1], y: [2] }], { width: 3000, height: 300 }, VH, 1000)
    expect(wide.layout.width).toBe(1000)
    expect(fitChartHeight([{ type: 'bar', x: [1], y: [2] }], { width: 600, height: 300 }, VH, 1000).layout.width).toBe(600)
  })
  it('caps charts without category rows and does not mutate its input', () => {
    const input = { height: 5000, yaxis: { title: 'v' } }
    const { layout } = fitChartHeight([{ type: 'scatter', x: [1, 2], y: [3, 4] }], input, VH)
    expect(layout.height).toBe(720)
    expect(input.height).toBe(5000)
  })
  it('wrapper sets and clears the scroll box on the element', () => {
    const lib = { newPlot: vi.fn(), react: vi.fn() }
    const P = withFittedLabels(lib)
    const el = document.createElement('div')
    P.newPlot(el, bar(400), { height: 9000 })
    expect(el.style.maxHeight).not.toBe('')
    expect(el.style.overflowY).toBe('auto')
    expect(el.getAttribute('tabindex')).toBe('0')
    P.react(el, bar(5), { height: 300 })
    expect(el.style.maxHeight).toBe('')
    expect(el.hasAttribute('tabindex')).toBe(false)
  })
})

describe('mergeLineTraces', () => {
  const edge = (i, color = 'grey', width = 1.2, dash = 'solid') => ({
    type: 'scatter', mode: 'lines', x: [i, i + 1, null], y: [0, 1, null],
    line: { color, width, dash }, hoverinfo: 'skip', showlegend: false,
  })
  const nodes = { type: 'scatter', mode: 'markers+text', x: [0, 1], y: [0, 1], text: ['a', 'b'] }

  it('turns thousands of edge traces into one per style, before the nodes', () => {
    const edges = [
      ...Array.from({ length: 3000 }, (_, i) => edge(i, 'grey', 1.2)),
      ...Array.from({ length: 1500 }, (_, i) => edge(i, 'red', 2.9, 'dash')),
    ]
    const out = mergeLineTraces([...edges, nodes])
    expect(out).toHaveLength(3)
    expect(out[2]).toBe(nodes)
    expect(out[0].x).toHaveLength(3000 * 3)
    expect(out[0].line).toEqual({ color: 'grey', width: 1, dash: 'solid' })
    expect(out[1].line).toEqual({ color: 'red', width: 3, dash: 'dash' })
    expect(out[0].x.slice(0, 6)).toEqual([0, 1, null, 1, 2, null]) // segments stay separate
    expect(edges[0].x).toEqual([0, 1, null]) // inputs untouched
  })
  it('adds the separator when an edge does not end with null', () => {
    const edges = Array.from({ length: 60 }, (_, i) => ({ ...edge(i), x: [i, i + 1], y: [0, 1] }))
    const out = mergeLineTraces(edges)
    expect(out).toHaveLength(1)
    expect(out[0].x.slice(0, 5)).toEqual([0, 1, null, 1, 2])
  })
  it('leaves ordinary charts alone', () => {
    const few = [edge(0), edge(1), nodes]
    expect(mergeLineTraces(few)).toBe(few)
    const lines = Array.from({ length: 80 }, (_, i) => ({ type: 'scatter', mode: 'lines', x: [0, 1], y: [i, i], name: `series ${i}` }))
    expect(mergeLineTraces(lines)).toBe(lines) // named, hoverable series are data, not edges
  })
})
