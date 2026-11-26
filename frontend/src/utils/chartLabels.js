/**
 * Keep long feature names from stretching charts.
 *
 * Feature names are often full lineages
 * ("msp_0001;Eukaryota;Heterokonta;…;Blastocystis sp. subtype 3"). Printed whole
 * on an axis or in a legend they force Plotly to widen the margins until the plot
 * itself is squeezed. `fitLongLabels` shortens what is *displayed* and leaves the
 * data alone: the category value stays the full name, so hover still shows it and
 * two features can never collapse into one category.
 */

export const MAX_LABEL_CHARS = 36
const MAX_TICKS = 80
const MAX_POINT_LABELS = 30   // labels drawn next to points before they pile up

// "msp_0001", "OTU123", "ASV_17", "K00001" …
const ID_RE = /^[A-Za-z][A-Za-z0-9]*[_-]?\d+[A-Za-z0-9]*$/
// rank prefixes used by MetaPhlAn/GTDB-style lineages: "s__", "g__", "d__" …
const RANK_PREFIX_RE = /^[a-z]__/

/** "Blastocystis sp. subtype 3" → "B. sp. subtype 3" */
export function abbreviateSpecies(species) {
  const words = String(species || '').trim().split(/\s+/)
  if (words.length >= 2 && /^[A-Z][a-z]{3,}$/.test(words[0])) {
    return `${words[0][0]}. ${words.slice(1).join(' ')}`
  }
  return words.join(' ')
}

/** Shorten in the middle so both the start (id) and the end (species) stay readable. */
export function ellipsize(text, max = MAX_LABEL_CHARS) {
  const s = String(text)
  if (s.length <= max) return s
  const head = Math.ceil((max - 1) * 0.6)
  const tail = max - 1 - head
  return `${s.slice(0, head).trimEnd()}…${s.slice(s.length - tail).trimStart()}`
}

/** True for "a;b;c" or "a|b|c" lineage-style names. */
export function isLineage(name) {
  return typeof name === 'string' && name.split(/[;|]/).filter(p => p.trim()).length >= 3
}

/**
 * Short display form of a feature name.
 *   "msp_0001;Eukaryota;…;Blastocystis sp. subtype 3" → "msp_0001 B. sp. subtype 3"
 *   "k__Bacteria|…|s__Faecalibacterium_prausnitzii"   → "F. prausnitzii"
 * Anything else is only ellipsized when longer than `max`.
 */
export function shortFeatureName(name, max = MAX_LABEL_CHARS) {
  if (typeof name !== 'string') return name
  let label = name.trim()
  if (isLineage(label)) {
    const parts = label.split(/[;|]/).map(p => p.trim()).filter(Boolean)
    const clean = p => p.replace(RANK_PREFIX_RE, '').replace(/_/g, ' ').trim()
    const first = parts[0]
    const last = abbreviateSpecies(clean(parts[parts.length - 1]))
    label = ID_RE.test(first) ? `${first} ${last}` : last
  }
  return ellipsize(label, max)
}

/** Indices of the `n` points with the largest markers (the first `n` when sizes are equal). */
function largestPoints(trace, n) {
  const sizes = Array.isArray(trace.marker?.size) ? trace.marker.size : null
  const order = trace.text.map((_, i) => i).filter(i => trace.text[i] !== '' && trace.text[i] != null)
  if (sizes) order.sort((a, b) => (Number(sizes[b]) || 0) - (Number(sizes[a]) || 0))
  return new Set(order.slice(0, n))
}

/** Text used as a Plotly template must not be read as a `%{…}` placeholder. */
function literal(text) {
  return typeof text === 'string' ? text.replace(/%\{/g, '% {') : text
}

function isLongText(v, max) {
  return typeof v === 'string' && v.length > max && Number.isNaN(Number(v))
}

function axisKey(ref, letter) {
  // trace.xaxis is "x", "x2", …  → layout key "xaxis", "xaxis2", …
  const n = typeof ref === 'string' ? ref.replace(/^[xy]/, '') : ''
  return `${letter}axis${n}`
}

function flatten(values) {
  if (!Array.isArray(values)) return []
  // multi-category axes pass [[outer…], [inner…]]; leave those alone
  return Array.isArray(values[0]) ? [] : values
}

/**
 * Return `[data, layout]` with long category tick labels and legend names
 * shortened. Inputs are not mutated.
 */
export function fitLongLabels(data, layout, max = MAX_LABEL_CHARS) {
  if (!Array.isArray(data)) return [data, layout]
  const outLayout = { ...(layout || {}) }
  const categories = {} // axis key -> ordered unique long-capable string values

  const outData = data.map((trace) => {
    if (!trace || typeof trace !== 'object') return trace
    for (const letter of ['x', 'y']) {
      const values = flatten(trace[letter])
      if (!values.some(v => isLongText(v, max))) continue
      const key = axisKey(trace[`${letter}axis`], letter)
      const seen = (categories[key] ||= new Map())
      for (const v of values) if (typeof v === 'string' && !seen.has(v)) seen.set(v, true)
    }
    let out = trace
    if (isLongText(trace.name, max)) out = { ...out, name: shortFeatureName(trace.name, max) }
    // Text drawn on the plot itself (node labels, point labels). `text` is left
    // whole so hover keeps the full name; what is *drawn* goes through
    // `texttemplate`: shortened, and on a crowded plot only for the largest points.
    if (typeof trace.mode === 'string' && trace.mode.includes('text')
        && Array.isArray(trace.text) && trace.texttemplate === undefined) {
      const long = trace.text.some(t => isLongText(t, max))
      // Only points that actually carry a label count (charts often label a chosen few).
      const crowded = trace.text.filter(t => t !== '' && t != null).length > MAX_POINT_LABELS
      if (long || crowded) {
        const keep = crowded ? largestPoints(trace, MAX_POINT_LABELS) : null
        out = {
          ...out,
          texttemplate: trace.text.map((t, i) => (keep && !keep.has(i) ? '' : literal(shortFeatureName(t, max)))),
        }
      }
    }
    return out
  })

  // Category axes: keep the values, replace only the text drawn at each tick.
  for (const [key, seen] of Object.entries(categories)) {
    const axis = { ...(outLayout[key] || {}) }
    if (axis.type && axis.type !== 'category') continue
    if (Array.isArray(axis.ticktext)) continue // handled below
    let vals = [...seen.keys()]
    if (vals.length > MAX_TICKS) {
      const step = Math.ceil(vals.length / MAX_TICKS)
      vals = vals.filter((_, i) => i % step === 0)
    }
    axis.tickmode = 'array'
    axis.tickvals = vals
    axis.ticktext = vals.map(v => shortFeatureName(v, max))
    outLayout[key] = axis
  }

  // Axes whose tick text was set by the caller (numeric positions + names).
  for (const key of Object.keys(outLayout)) {
    if (!/^[xy]axis\d*$/.test(key)) continue
    const axis = outLayout[key]
    if (!axis || !Array.isArray(axis.ticktext)) continue
    if (axis.ticktext.some(t => isLongText(t, max))) {
      outLayout[key] = { ...axis, ticktext: axis.ticktext.map(t => (typeof t === 'string' ? shortFeatureName(t, max) : t)) }
    }
  }

  return [outData, outLayout]
}

// ---------------------------------------------------------------------------
// Chart height
// ---------------------------------------------------------------------------

const MIN_ROW_PX = 12        // tightest row that still takes a 10 px label
const COMFORT_ROW_PX = 16    // row height used inside a scrolling chart
const DEFAULT_V_MARGIN = 110

/** Tallest a chart may be drawn: most of the window, within sane bounds. */
export function maxChartHeight(viewportHeight) {
  const vh = viewportHeight || (typeof window !== 'undefined' ? window.innerHeight : 900) || 900
  return Math.max(420, Math.min(900, Math.round(vh * 0.8)))
}

function verticalMargin(layout) {
  const m = layout?.margin
  if (!m || (m.t == null && m.b == null)) return DEFAULT_V_MARGIN
  return (m.t ?? 60) + (m.b ?? 50)
}

/** Number of category rows on the primary y axis (0 when y is numeric). */
function countRows(data) {
  let rows = 0
  let heatmapOnly = data.length > 0
  for (const trace of data) {
    if (!trace || typeof trace !== 'object') continue
    if (trace.yaxis && trace.yaxis !== 'y') continue
    const isHeatmap = trace.type === 'heatmap'
    if (!isHeatmap) heatmapOnly = false
    const y = flatten(trace.y)
    if (y.length && y.some(v => typeof v === 'string' && Number.isNaN(Number(v)))) {
      rows = Math.max(rows, new Set(y).size)
    } else if (isHeatmap && Array.isArray(trace.z) && !y.length) {
      rows = Math.max(rows, trace.z.length)
    } else if (isHeatmap && y.length) {
      rows = Math.max(rows, new Set(y).size)
    }
  }
  return { rows, heatmapOnly }
}

/**
 * Keep a chart within the window.
 *
 * Charts with one row per feature (or per sample) ask for `rows × n px`, which
 * has no upper limit: 179 features made a 5,000 px chart and 734 samples a
 * 10,000 px one. Given the requested layout this returns
 * `{ layout, scrollHeight }`:
 *
 * - it fits                      → unchanged;
 * - rows fit at ≥ 12 px each     → drawn at the maximum height, smaller tick font;
 * - a heatmap                    → always drawn at the maximum height; tick labels
 *                                  are thinned when rows are too thin for one each
 *                                  (hover and zoom give the detail);
 * - otherwise (a long list)      → drawn at 16 px per row inside a box that
 *                                  scrolls (`scrollHeight`), every row labelled.
 *
 * A fixed `width` larger than `maxWidth` is cut back the same way.
 */
export function fitChartHeight(data, layout, viewportHeight, maxWidth) {
  const sized = fitHeight(data, layout, viewportHeight)
  return { ...sized, layout: fitWidth(data, sized.layout, layout, maxWidth) }
}

function thinAxis(axis, keep) {
  const out = { ...(axis || {}) }
  if (Array.isArray(out.tickvals)) {
    if (out.tickvals.length > keep) {
      const step = Math.ceil(out.tickvals.length / keep)
      const pick = (_, i) => i % step === 0
      if (Array.isArray(out.ticktext)) out.ticktext = out.ticktext.filter(pick)
      out.tickvals = out.tickvals.filter(pick)
    }
  } else {
    out.nticks = keep
  }
  return out
}

/** A chart must never be wider than the space it sits in (it would widen the whole page). */
function fitWidth(data, layout, original, maxWidth) {
  const requested = layout?.width
  if (!Array.isArray(data) || typeof requested !== 'number' || !maxWidth || requested <= maxWidth) return layout
  const out = { ...layout }
  // A square matrix stays roughly square once its height has been capped.
  const wasSquare = typeof original?.height === 'number' && Math.abs(original.height - original.width) < 2
  out.width = wasSquare && typeof out.height === 'number' ? Math.min(maxWidth, out.height + 160) : maxWidth
  const m = out.margin || {}
  const plotW = out.width - ((m.l ?? 80) + (m.r ?? 80))
  out.xaxis = thinAxis(out.xaxis, Math.max(1, Math.floor(plotW / 14)))
  return out
}

/** Ordered unique category names on the primary y axis. */
function yCategories(data) {
  const seen = new Map()
  for (const trace of data) {
    if (!trace || typeof trace !== 'object' || (trace.yaxis && trace.yaxis !== 'y')) continue
    for (const v of flatten(trace.y)) if (typeof v === 'string' && !seen.has(v)) seen.set(v, true)
  }
  return [...seen.keys()]
}

function fitHeight(data, layout, viewportHeight) {
  const requested = layout?.height
  const maxH = maxChartHeight(viewportHeight)
  if (!Array.isArray(data) || typeof requested !== 'number' || requested <= maxH) {
    return { layout, scrollHeight: null }
  }
  const counted = countRows(data)
  const heatmapOnly = counted.heatmapOnly
  // Rows placed at numeric positions with their names given as tick text.
  const labelled = Array.isArray(layout.yaxis?.ticktext) ? layout.yaxis.ticktext.length : 0
  const rows = Math.max(counted.rows, labelled)
  const margin = verticalMargin(layout)
  const out = { ...layout }
  if (rows === 0) {
    out.height = maxH
    return { layout: out, scrollHeight: null }
  }

  const yaxis = { ...(out.yaxis || {}) }
  const smallTicks = () => { yaxis.tickfont = { ...(yaxis.tickfont || {}), size: Math.min(yaxis.tickfont?.size || 12, 10) } }
  const rowPxAtMax = (maxH - margin) / rows

  if (rowPxAtMax >= MIN_ROW_PX) {
    out.height = maxH
    if (rowPxAtMax < 15) smallTicks()
    out.yaxis = yaxis
    return { layout: out, scrollHeight: null }
  }

  // A heatmap is read as a picture, not row by row: it always fits the window.
  // Labels are thinned once rows get too thin to carry one each.
  if (heatmapOnly) {
    out.height = maxH
    smallTicks()
    const keep = Math.max(1, Math.floor((maxH - margin) / MIN_ROW_PX))
    out.yaxis = thinAxis(yaxis, keep)
    return { layout: out, scrollHeight: null }
  }

  // A long list that is meant to be read: keep rows legible and scroll the chart.
  out.height = Math.min(requested, rows * COMFORT_ROW_PX + margin)
  if (out.height <= maxH) {
    out.yaxis = yaxis
    return { layout: out, scrollHeight: null }
  }
  smallTicks()
  yaxis.tickfont.size = 11
  // The point of scrolling is to read every row: label them all, even when the
  // label pass thinned them for a chart it expected to be squeezed.
  const cats = yCategories(data)
  if (cats.length === rows && !(Array.isArray(layout.yaxis?.tickvals) && typeof layout.yaxis.tickvals[0] === 'number')) {
    yaxis.tickmode = 'array'
    yaxis.tickvals = cats
    yaxis.ticktext = cats.map(v => shortFeatureName(v))
    delete yaxis.nticks
  }
  out.yaxis = yaxis
  return { layout: out, scrollHeight: maxH }
}

// ---------------------------------------------------------------------------
// Many identical line traces (network edges)
// ---------------------------------------------------------------------------

const MERGE_THRESHOLD = 50

function isPlainEdge(t) {
  return t && typeof t === 'object'
    && (t.type === 'scatter' || t.type === undefined)
    && t.mode === 'lines'
    && t.hoverinfo === 'skip'
    && t.showlegend === false
    && Array.isArray(t.x) && Array.isArray(t.y)
    && !t.fill && !t.text && !t.customdata && !t.name
}

/**
 * Merge line-only, hover-less traces that share a style into one trace each.
 *
 * Network charts draw one trace per edge: thousands of traces make Plotly slow
 * to draw, to hover and to resize. Edges are grouped by axis, colour, dash and
 * width (rounded to 0.5 px) and each group becomes a single trace whose segments
 * are separated by nulls. Drawing order relative to other traces is kept.
 */
export function mergeLineTraces(data) {
  if (!Array.isArray(data)) return data
  if (data.filter(isPlainEdge).length < MERGE_THRESHOLD) return data
  const groups = new Map()
  const out = []
  for (const trace of data) {
    if (!isPlainEdge(trace)) { out.push(trace); continue }
    const line = trace.line || {}
    const width = Math.round((line.width ?? 2) * 2) / 2
    const key = [trace.xaxis || 'x', trace.yaxis || 'y', line.color, line.dash || 'solid', width, trace.opacity ?? 1].join('|')
    let merged = groups.get(key)
    if (!merged) {
      merged = { ...trace, x: [], y: [], line: { ...line, width } }
      groups.set(key, merged)
      out.push(merged) // takes the place of the group's first edge
    }
    merged.x.push(...trace.x)
    merged.y.push(...trace.y)
    if (trace.x[trace.x.length - 1] !== null) { merged.x.push(null); merged.y.push(null) }
  }
  return out
}

function resolveNode(el) {
  return typeof el === 'string' && typeof document !== 'undefined' ? document.getElementById(el) : el
}

/** Width the chart's container offers (0 when it cannot be measured, e.g. not laid out yet). */
function availableWidth(el) {
  const node = resolveNode(el)
  const own = node?.clientWidth || node?.parentElement?.clientWidth || 0
  if (own) return own
  return typeof window !== 'undefined' && window.innerWidth ? window.innerWidth - 64 : 0
}

function applyScrollBox(el, scrollHeight) {
  const node = resolveNode(el)
  if (!node || !node.style) return
  if (scrollHeight) {
    node.style.maxHeight = `${scrollHeight}px`
    node.style.overflowY = 'auto'
    node.style.overflowX = 'hidden'
    node.setAttribute('tabindex', '0') // scrollable regions must be reachable by keyboard
  } else if (node.style.maxHeight) {
    node.style.maxHeight = ''
    node.style.overflowY = ''
    node.style.overflowX = ''
    node.removeAttribute('tabindex')
  }
}

/** Wrap a Plotly module so every newPlot/react call gets labels and height fitted. */
export function withFittedLabels(plotly) {
  const fit = (el, data, layout) => {
    const [d, l] = fitLongLabels(mergeLineTraces(data), layout)
    const { layout: sized, scrollHeight } = fitChartHeight(d, l, undefined, availableWidth(el))
    applyScrollBox(el, scrollHeight)
    return [d, sized]
  }
  const wrap = method => (el, data, layout, ...rest) => {
    if (Array.isArray(data)) {
      const [d, l] = fit(el, data, layout)
      return plotly[method](el, d, l, ...rest)
    }
    // figure-object form: newPlot(el, { data, layout, config })
    if (data && typeof data === 'object' && Array.isArray(data.data)) {
      const [d, l] = fit(el, data.data, data.layout)
      return plotly[method](el, { ...data, data: d, layout: l }, layout, ...rest)
    }
    return plotly[method](el, data, layout, ...rest)
  }
  const newPlot = wrap('newPlot')
  const react = wrap('react')
  return new Proxy(plotly, {
    get(target, prop) {
      if (prop === 'newPlot') return newPlot
      if (prop === 'react') return react
      return target[prop]
    },
  })
}
