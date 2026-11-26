/**
 * Two-dimensional histogram for density heatmaps.
 *
 * Plotly's histogram2d colours empty bins with the bottom of the colour scale, so
 * a sparse search space looks filled in. Binning here lets empty bins be `null`
 * (not drawn: the background shows) while bins with at least one point are coloured.
 */

function edges(values, n, integer) {
  let lo = Math.min(...values)
  let hi = Math.max(...values)
  if (integer) {
    // one bin per integer value when there are few of them, never splitting an integer
    const span = hi - lo + 1
    const width = Math.max(1, Math.ceil(span / n))
    const count = Math.ceil(span / width)
    return { lo: lo - 0.5, width, count }
  }
  if (lo === hi) { lo -= 0.5; hi += 0.5 }
  return { lo, width: (hi - lo) / n, count: n }
}

function index(v, e) {
  const i = Math.floor((v - e.lo) / e.width)
  return Math.min(e.count - 1, Math.max(0, i))
}

/**
 * @param {number[]} xs
 * @param {number[]} ys
 * @param {{ nx?: number, ny?: number, integerX?: boolean }} [options]
 * @returns {{ x: number[], y: number[], z: (number|null)[][], max: number }}
 *   bin centres and counts, z[row = y bin][column = x bin], null where empty.
 */
export function densityGrid(xs, ys, { nx = 40, ny = 40, integerX = false } = {}) {
  const pts = []
  for (let i = 0; i < Math.min(xs.length, ys.length); i++) {
    if (Number.isFinite(xs[i]) && Number.isFinite(ys[i])) pts.push([xs[i], ys[i]])
  }
  if (!pts.length) return { x: [], y: [], z: [], max: 0 }
  const ex = edges(pts.map(p => p[0]), nx, integerX)
  const ey = edges(pts.map(p => p[1]), ny, false)
  const counts = Array.from({ length: ey.count }, () => new Array(ex.count).fill(0))
  for (const [x, y] of pts) counts[index(y, ey)][index(x, ex)] += 1
  let max = 0
  const z = counts.map(row => row.map(c => { if (c > max) max = c; return c > 0 ? c : null }))
  const centre = (e, i) => e.lo + (i + 0.5) * e.width
  return {
    x: Array.from({ length: ex.count }, (_, i) => centre(ex, i)),
    y: Array.from({ length: ey.count }, (_, i) => centre(ey, i)),
    z,
    max,
  }
}
