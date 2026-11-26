/**
 * Lists user-facing text written directly in Vue templates (text nodes and
 * title / placeholder / aria-label / alt attributes) instead of going through i18n.
 * Proper nouns and code samples will show up too: read the list, don't gate on it.
 *
 *   node tools/text-scan.mjs [--summary] [path-fragment]     (npm run check:text)
 */
import { parse } from '@vue/compiler-sfc'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

const ATTRS = new Set(['title', 'placeholder', 'aria-label', 'alt', 'label'])
const files = []
;(function walk(d) {
  for (const f of readdirSync(d)) {
    const p = join(d, f)
    if (statSync(p).isDirectory()) { if (f !== '__tests__') walk(p) } else if (f.endsWith('.vue')) files.push(p)
  }
})('src')

const letters = /[A-Za-zÀ-ÿ]{2,}/
let total = 0
const only = process.argv.slice(2).find(a => !a.startsWith('--'))
for (const file of files) {
  if (only && !file.includes(only)) continue
  const { descriptor } = parse(readFileSync(file, 'utf8'))
  const ast = descriptor.template?.ast
  if (!ast) continue
  const hits = []
  ;(function visit(node) {
    if (node.type === 2) { // TEXT
      const t = node.content.trim()
      if (letters.test(t) && !/^&[a-z#0-9]+;$/.test(t)) hits.push([node.loc.start.line, 'text', t.slice(0, 90)])
    } else if (node.type === 1) {
      if (node.tag === 'code' || node.tag === 'pre' || node.tag === 'kbd') { /* literal by nature */ }
      for (const p of node.props || []) {
        if (p.type === 6 && ATTRS.has(p.name) && p.value && letters.test(p.value.content)) hits.push([p.loc.start.line, p.name, p.value.content.slice(0, 90)])
      }
      for (const c of node.children || []) visit(c)
    } else if (node.children) {
      for (const c of node.children) visit(c)
    } else if (node.branches) {
      for (const b of node.branches) visit(b)
    }
  })(ast)
  if (hits.length) {
    total += hits.length
    if (process.argv.includes('--summary')) console.log(String(hits.length).padStart(4), file)
    else for (const h of hits) console.log(`${file}:${h[0]} [${h[1]}] ${h[2]}`)
  }
}
console.log('TOTAL', total)
