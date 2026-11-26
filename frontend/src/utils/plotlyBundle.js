/**
 * Custom Plotly build: the core plus only the trace types this app draws.
 *
 * The full distribution is 4.8 MB; this one carries scatter (in core), bar,
 * heatmap, histogram2d, violin, scatterpolar, waterfall and sankey.
 * 3-D scatter (WebGL) is a separate chunk, see plotly3d.js.
 *
 * Adding a chart with a new `type:` means registering its module here —
 * Plotly otherwise warns "Unrecognized trace type" and draws nothing.
 */
import Plotly from 'plotly.js/lib/core'
import bar from 'plotly.js/lib/bar'
import heatmap from 'plotly.js/lib/heatmap'
import histogram2d from 'plotly.js/lib/histogram2d'
import violin from 'plotly.js/lib/violin'
import scatterpolar from 'plotly.js/lib/scatterpolar'
import waterfall from 'plotly.js/lib/waterfall'
import sankey from 'plotly.js/lib/sankey'

Plotly.register([bar, heatmap, histogram2d, violin, scatterpolar, waterfall, sankey])

/** Trace types available after loadPlotlyLib(). */
export const TRACE_TYPES_2D = ['scatter', 'bar', 'heatmap', 'histogram2d', 'violin', 'scatterpolar', 'waterfall', 'sankey']

export default Plotly
