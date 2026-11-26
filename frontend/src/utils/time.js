/** Shared relative-time and duration formatting (translated). */
import i18n from '../i18n'

export function timeAgo(value) {
  if (!value) return ''
  const then = new Date(value).getTime()
  if (Number.isNaN(then)) return ''
  const { t } = i18n.global
  const s = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (s < 60) return t('time.justNow')
  const m = Math.floor(s / 60)
  if (m < 60) return t('time.minutesAgo', { n: m })
  const h = Math.floor(m / 60)
  if (h < 24) return t('time.hoursAgo', { n: h })
  const d = Math.floor(h / 24)
  if (d < 30) return t('time.daysAgo', { n: d })
  const locale = typeof i18n.global.locale === 'string' ? i18n.global.locale : i18n.global.locale.value
  return new Date(value).toLocaleDateString(locale)
}
