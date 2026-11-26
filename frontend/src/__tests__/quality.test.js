/**
 * Whole-codebase checks: accessibility of templates, colour contrast of the
 * theme, translation hygiene, chart colours, and the API module.
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { scanDir } from '../../tools/a11y-scan.mjs'
import { checkContrast, MIN_RATIO } from '../../tools/contrast.mjs'
import en from '../i18n/locales/en.json'
import fr from '../i18n/locales/fr.json'
import { chartKey } from '../utils/chartText'
import * as apiModule from '../api'

const SRC = path.resolve(__dirname, '..')

function walk(dir, exts = ['.vue', '.js']) {
  const out = []
  for (const f of fs.readdirSync(dir)) {
    const p = path.join(dir, f)
    if (fs.statSync(p).isDirectory()) { if (f !== '__tests__') out.push(...walk(p, exts)) } else if (exts.some(e => f.endsWith(e))) out.push(p)
  }
  return out
}
function flatten(obj, prefix = '', out = {}) {
  for (const [k, v] of Object.entries(obj)) {
    if (v && typeof v === 'object') flatten(v, `${prefix}${k}.`, out)
    else out[prefix + k] = v
  }
  return out
}
const rel = (p) => path.relative(SRC, p)

describe('accessibility of templates', () => {
  it('no click handler on a non-interactive element, every control and icon button has a name', () => {
    const hits = scanDir(SRC).map(h => `${rel(h.file)}:${h.line} [${h.kind}] ${h.detail}`)
    expect(hits).toEqual([])
  })

  it('content text is never smaller than 0.75rem', () => {
    const small = []
    for (const file of walk(SRC, ['.vue'])) {
      const text = fs.readFileSync(file, 'utf8')
      for (const m of text.matchAll(/font-size:\s*(0?\.\d+)rem/g)) if (parseFloat(m[1]) < 0.75) small.push(`${rel(file)}: ${m[0]}`)
    }
    expect(small).toEqual([])
  })

  it('status colours used for text are the dark variants', () => {
    const light = []
    for (const file of walk(SRC, ['.vue'])) {
      const text = fs.readFileSync(file, 'utf8')
      if (/(?<![-\w])color:\s*var\(--(success|warning)\)/.test(text)) light.push(rel(file))
    }
    expect(light).toEqual([])
  })
})

describe('theme contrast', () => {
  it('every text token reaches 4.5:1 on every surface, in both themes', () => {
    const rows = checkContrast(fs.readFileSync(path.join(SRC, 'App.vue'), 'utf8'))
    expect(rows.length).toBeGreaterThan(20)
    expect(rows.filter(r => r.worst < MIN_RATIO).map(r => `${r.theme} --${r.token} ${r.worst.toFixed(2)}`)).toEqual([])
  })
})

describe('translations', () => {
  const enFlat = flatten(en)
  const frFlat = flatten(fr)

  it('the two locales have identical key sets', () => {
    expect(Object.keys(enFlat).sort()).toEqual(Object.keys(frFlat).sort())
  })

  it('no key is left that nothing uses', () => {
    // Keys reached through a computed name (status, tab id, parameter, preset…).
    const dynamic = ['paramErrors.', 'params.', 'paramCategories.', 'parameters.presets.', 'parameters.sweep.',
      'nav.themeMode.', 'home.uc.', 'home.ucStat.', 'admin.defaultField.', 'errors.', 'notify.', 'time.', 'checklist.steps.']
    const dynamicKeys = new Set(['common.pending', 'common.running', 'common.completed', 'common.failed', 'common.cancelled',
      'data.prevalence', 'data.abundance', 'data.barcode', 'data.classHeatmap', 'data.volcano', 'data.pcoa'])
    const literals = new Set()
    const chartKeys = new Set()
    for (const file of walk(SRC)) {
      const text = fs.readFileSync(file, 'utf8')
      for (const m of text.matchAll(/['"`]((?:[a-z][A-Za-z0-9]*\.)+[A-Za-z0-9_]+)['"`]/g)) literals.add(m[1])
      for (const m of text.matchAll(/\bct\(\s*(['"])((?:\\.|(?!\1).)*)\1\s*\)/g)) chartKeys.add(chartKey(m[2].replace(/\\'/g, "'")))
    }
    const unused = Object.keys(enFlat).filter(k =>
      !literals.has(k) && !chartKeys.has(k) && !dynamicKeys.has(k) && !dynamic.some(p => k.startsWith(p)))
    expect(unused).toEqual([])
  })

  it('every chart text passed to ct() has a French translation', () => {
    const missing = []
    for (const file of walk(SRC)) {
      const text = fs.readFileSync(file, 'utf8')
      for (const m of text.matchAll(/\bct\(\s*(['"])((?:\\.|(?!\1).)*)\1\s*\)/g)) {
        const key = chartKey(m[2].replace(/\\'/g, "'"))
        if (!(key in frFlat)) missing.push(`${rel(file)}: ${m[2]}`)
      }
    }
    expect(missing).toEqual([])
  })
})

describe('chart colours', () => {
  it('chart code takes its colours from the theme, not from literals', () => {
    const files = [
      'composables/useResultsTab.js', 'views/DataTab.vue', 'views/MetaAnalysisView.vue', 'views/SignatureZooView.vue',
      ...fs.readdirSync(path.join(SRC, 'components/results')).filter(f => f.endsWith('.vue')).map(f => `components/results/${f}`),
    ]
    const offenders = []
    for (const f of files) {
      let text = fs.readFileSync(path.join(SRC, f), 'utf8')
      if (f.endsWith('.vue')) text = (/<script[^>]*>([\s\S]*?)<\/script>/.exec(text) || [])[1] || ''
      text.split('\n').forEach((line, i) => {
        if (/^\s*(\/\/|\*)/.test(line)) return
        // The barcode palette is a fixed, documented Viridis sample.
        if (/Viridis|dataColors = \[/.test(line)) return
        if (/['"`]#[0-9a-fA-F]{3,8}['"`]|['"`]rgba?\(/.test(line)) offenders.push(`${f}:${i + 1} ${line.trim().slice(0, 80)}`)
      })
    }
    expect(offenders).toEqual([])
  })
})

describe('api module', () => {
  it('components do not call axios directly', () => {
    const allowed = new Set(['api/index.js', 'utils/http.js', 'stores/auth.js'])
    const direct = []
    for (const file of walk(SRC)) {
      if (allowed.has(rel(file))) continue
      if (/\baxios\.(get|post|put|patch|delete|request)\(/.test(fs.readFileSync(file, 'utf8'))) direct.push(rel(file))
    }
    expect(direct).toEqual([])
  })

  it('path parameters are URL-encoded and bodies go in the right position', async () => {
    const calls = []
    const { http, api } = apiModule
    const original = { get: http.get, post: http.post }
    http.get = (url, config) => { calls.push(['get', url, config]); return Promise.resolve({ data: {} }) }
    http.post = (url, body, config) => { calls.push(['post', url, body, config]); return Promise.resolve({ data: {} }) }
    try {
      await api.analysis.jobLogs('p/1', 'j 2', { params: { offset: 10 } })
      await api.analysis.run('p1', { general: {} }, { params: { x_file_id: 'f' } })
      await api.admin.restoreBackup('replace', 'FORM')
    } finally {
      Object.assign(http, original)
    }
    expect(calls[0]).toEqual(['get', '/api/analysis/p%2F1/jobs/j%202/logs', { params: { offset: 10 } }])
    expect(calls[1]).toEqual(['post', '/api/analysis/p1/run', { general: {} }, { params: { x_file_id: 'f' } }])
    expect(calls[2]).toEqual(['post', '/api/admin/restore?mode=replace', 'FORM', undefined])
  })

  it('has one function per endpoint, each documented', () => {
    const text = fs.readFileSync(path.join(SRC, 'api/index.js'), 'utf8')
    const fns = [...text.matchAll(/^ {2}(\w+): \(/gm)].length
    const docs = [...text.matchAll(/^ {2}\/\*\* (GET|POST|PUT|PATCH|DELETE) /gm)].length
    expect(fns).toBeGreaterThan(110)
    expect(docs).toBe(fns)
  })
})
