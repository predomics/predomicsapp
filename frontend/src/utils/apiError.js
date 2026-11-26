/**
 * Turn any failed request into one human-readable message.
 *
 * The backend answers errors as {"error": {"code", "message"}}; FastAPI
 * validation errors (422) still use {"detail": [...]} and a few legacy
 * endpoints {"detail": "..."}.
 *
 * Calling apiError(e) also marks the error as handled, which tells the global
 * axios interceptor (utils/http.js) NOT to show its own toast: the caller owns
 * the message, so the user sees it exactly once.
 */
import i18n from '../i18n'

function tr(key, fallback, params) {
  try {
    const { t, te } = i18n.global
    if (te(key)) return params ? t(key, params) : t(key)
  } catch { /* fall through to the English text */ }
  return params ? fallback.replace(/\{(\w+)\}/g, (m, name) => (name in params ? String(params[name]) : m)) : fallback
}

function formatDetailArray(detail) {
  return detail
    .map((d) => {
      if (typeof d === 'string') return d
      if (!d || typeof d !== 'object') return ''
      const loc = Array.isArray(d.loc)
        ? d.loc.filter((p) => p !== 'body' && p !== 'query' && p !== 'path').join('.')
        : ''
      const msg = d.msg || d.message || ''
      return loc && msg ? `${loc}: ${msg}` : msg || loc
    })
    .filter(Boolean)
    .join('; ')
}

/** Seconds the server asked us to wait (Retry-After header), or 0. */
export function retryAfterSeconds(e) {
  const h = e?.response?.headers
  const raw = h && (typeof h.get === 'function' ? h.get('retry-after') : h['retry-after'])
  const n = parseInt(raw, 10)
  return Number.isFinite(n) && n > 0 ? n : 0
}

/** Machine-readable error code from {"error": {"code"}} (e.g. "EMAIL_NOT_VERIFIED"), or ''. */
export function apiErrorCode(e) {
  const code = e?.response?.data?.error?.code
  return typeof code === 'string' ? code : ''
}

/** The server's X-Request-ID for this response, so a user can quote it in a bug report. */
export function requestId(e) {
  const h = e?.response?.headers
  const raw = h && (typeof h.get === 'function' ? h.get('x-request-id') : h['x-request-id'])
  return typeof raw === 'string' && raw ? raw : ''
}

/** Extract the message without marking the error as handled. Server errors (5xx) carry their request reference. */
export function extractApiError(e, fallback = '') {
  const msg = baseMessage(e, fallback)
  const id = (e?.response?.status ?? 0) >= 500 ? requestId(e) : ''
  return id ? `${msg} ${tr('errors.requestRef', '(reference: {id})', { id })}` : msg
}

function baseMessage(e, fallback = '') {
  if (!e) return fallback || tr('errors.generic', 'Something went wrong. Please try again.')
  const data = e.response?.data
  const status = e.response?.status

  if (data && typeof data === 'object') {
    const err = data.error
    if (err && typeof err === 'object' && typeof err.message === 'string' && err.message) return err.message
    if (typeof err === 'string' && err) return err
    const detail = data.detail
    if (typeof detail === 'string' && detail) return detail
    if (Array.isArray(detail) && detail.length) {
      const joined = formatDetailArray(detail)
      if (joined) return joined
    }
    if (detail && typeof detail === 'object' && typeof detail.message === 'string') return detail.message
    if (typeof data.message === 'string' && data.message) return data.message
  }

  if (status === 429) {
    const wait = retryAfterSeconds(e)
    if (wait) return tr('errors.tooManyRequestsRetry', 'Too many attempts. Try again in {s} seconds.', { s: wait })
    return tr('errors.tooManyRequests', 'Too many requests — please slow down.')
  }
  if (e.code === 'ECONNABORTED' || /timeout/i.test(e.message || '')) {
    return tr('errors.timeout', 'The server took too long to answer. Please try again.')
  }
  if (!e.response && (e.code === 'ERR_NETWORK' || e.request)) {
    return tr('errors.network', 'Cannot reach the server. Check your connection and try again.')
  }
  if (status === 413) return tr('errors.tooLarge', 'The file is too large.')
  if (status === 403) return fallback || tr('errors.forbidden', 'You are not allowed to do this.')
  if (status === 404) return fallback || tr('errors.notFound', 'Not found.')
  if (status >= 500) return fallback || tr('errors.server', 'The server ran into a problem. Please try again.')
  return fallback || e.message || tr('errors.generic', 'Something went wrong. Please try again.')
}

/** Message for the user; marks the error handled so no duplicate global toast fires. */
export function apiError(e, fallback = '') {
  if (e && typeof e === 'object') {
    try { e._handled = true } catch { /* frozen error */ }
  }
  return extractApiError(e, fallback)
}

/** Mark an error as deliberately ignored (no toast, no message). */
export function ignoreError(e) {
  if (e && typeof e === 'object') {
    try { e._handled = true } catch { /* frozen error */ }
  }
}
