/**
 * Accessibility check for Vue templates.
 *
 * Reports, per file:
 *   click    a click handler on an element that is not focusable/operable by keyboard
 *   control  an input / select / textarea with no accessible name
 *   button   a button whose only content is an icon or symbol and that has no aria-label
 *
 *   node tools/a11y-scan.mjs            list findings
 *   node tools/a11y-scan.mjs --strict   exit 1 if there are any   (npm run check:a11y)
 *
 * The same scan runs in the unit tests (src/__tests__/quality.test.js).
 */
import { parse } from '@vue/compiler-sfc'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const INTERACTIVE = new Set(['button', 'a', 'input', 'select', 'textarea', 'summary', 'label', 'option', 'router-link', 'details'])
const attr = (n, name) => n.props?.find(p => (p.type === 6 && p.name === name) || (p.type === 7 && p.name === 'bind' && p.arg?.content === name))
const hasOn = (n, ev) => n.props?.some(p => p.type === 7 && p.name === 'on' && p.arg?.content === ev)
const isComponent = (n) => /[A-Z]/.test(n.tag[0]) || (n.tag.includes('-') && n.tag !== 'router-link')
const textOf = (n) => {
  if (n.type === 2) return n.content
  if (n.type === 5) return '{{x}}'
  if (n.type === 1 && attr(n, 'aria-hidden')) return ''
  if (n.type === 1 && n.props?.some(p => p.type === 7 && (p.name === 'text' || p.name === 'html'))) return '{{x}}'
  return (n.children || []).map(textOf).join('')
}

/** Findings for one SFC source: [{ line, kind, detail }]. */
export function scanSource(source) {
  const { descriptor } = parse(source)
  const ast = descriptor.template?.ast
  if (!ast) return []
  const labelFor = new Set()
  ;(function collect(n) {
    if (n.type === 1 && (n.tag === 'label' || n.tag === 'component')) {
      const f = attr(n, 'for')
      if (f) labelFor.add(f.type === 6 ? f.value?.content : '*dyn*')
    }
    for (const c of n.children || []) collect(c)
  })(ast)
  const hits = []
  ;(function visit(n, inLabel) {
    if (n.type !== 1) { for (const c of n.children || []) visit(c, inLabel); return }
    const line = n.loc.start.line
    if (hasOn(n, 'click') && !INTERACTIVE.has(n.tag) && !isComponent(n) && n.tag !== 'template') {
      const role = attr(n, 'role'), tab = attr(n, 'tabindex')
      const click = n.props.find(p => p.type === 7 && p.name === 'on' && p.arg?.content === 'click')
      const backdrop = click?.modifiers?.some(m => (m.content || m) === 'self') || /overlay|backdrop/.test(attr(n, 'class')?.value?.content || '')
      const stopOnly = /^\s*$/.test(click?.exp?.content || '') // @click.stop with no handler
      const keyboard = tab && hasOn(n, 'keydown')
      if (!(role && tab) && !keyboard && !backdrop && !stopOnly) hits.push({ line, kind: 'click', detail: `<${n.tag}>` })
    }
    if (['input', 'select', 'textarea'].includes(n.tag)) {
      const type = attr(n, 'type')?.value?.content
      if (type !== 'hidden') {
        const id = attr(n, 'id')
        const named = attr(n, 'aria-label') || attr(n, 'aria-labelledby') || inLabel ||
          (id && (id.type === 7 ? labelFor.has('*dyn*') : labelFor.has(id.value?.content)))
        const hiddenFile = type === 'file' && (attr(n, 'hidden') || /hidden|sr-only/.test(attr(n, 'class')?.value?.content || '') || /display:\s*none/.test(attr(n, 'style')?.value?.content || ''))
        if (!named && !hiddenFile) hits.push({ line, kind: 'control', detail: `<${n.tag}${type ? ' type=' + type : ''}>` })
      }
    }
    if (n.tag === 'button') {
      const txt = textOf(n).replace(/&[a-z#0-9]+;/gi, '').replace(/[^\p{L}\p{N}{}]/gu, '')
      if (!txt && !attr(n, 'aria-label') && !attr(n, 'aria-labelledby')) hits.push({ line, kind: 'button', detail: 'no accessible name' })
    }
    for (const c of n.children || []) visit(c, inLabel || n.tag === 'label')
  })(ast, false)
  return hits
}

export function vueFiles(dir) {
  const out = []
  ;(function walk(d) {
    for (const f of readdirSync(d)) {
      const p = join(d, f)
      if (statSync(p).isDirectory()) { if (f !== '__tests__' && f !== 'node_modules') walk(p) } else if (f.endsWith('.vue')) out.push(p)
    }
  })(dir)
  return out.sort()
}

/** Findings for every .vue file under a directory: [{ file, line, kind, detail }]. */
export function scanDir(dir) {
  return vueFiles(dir).flatMap(file => scanSource(readFileSync(file, 'utf8')).map(h => ({ file, ...h })))
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const hits = scanDir('src')
  for (const h of hits) console.log(`${h.file}:${h.line} [${h.kind}] ${h.detail}`)
  console.log(`${hits.length} accessibility finding(s)`)
  if (process.argv.includes('--strict') && hits.length) process.exit(1)
}
