/**
 * Chart text (axis titles, legend entries) in the user's language.
 *
 *   ct('Generation')  → t('charts.generation'), falling back to the English text
 *
 * The English string is the key's source: a chart label added in code shows
 * as written until a translation is added under `charts.*` in the locales.
 */
import i18n from '../i18n'

export function chartKey(text) {
  return 'charts.' + String(text)
    .toLowerCase()
    .replace(/τ/g, 'tau')
    .replace(/\+/g, ' plus ')
    .replace(/[−-]/g, ' minus ')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .replace(/ (\w)/g, (_, c) => c.toUpperCase())
}

export function ct(text) {
  const key = chartKey(text)
  return i18n.global.te(key) ? i18n.global.t(key) : text
}
