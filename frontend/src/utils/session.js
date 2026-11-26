/**
 * Access-token lifetime helpers (the token is a JWT; nothing here verifies it —
 * the server does — we only read its timestamps to know when to renew it).
 */

/** Decode a JWT payload. Returns null for anything that is not a readable JWT. */
export function decodeJwt(token) {
  if (typeof token !== 'string') return null
  const parts = token.split('.')
  if (parts.length !== 3) return null
  try {
    const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4)
    const json = decodeURIComponent(
      atob(padded).split('').map((c) => '%' + c.charCodeAt(0).toString(16).padStart(2, '0')).join(''),
    )
    const payload = JSON.parse(json)
    return payload && typeof payload === 'object' ? payload : null
  } catch {
    return null
  }
}

/** Fraction of the lifetime that must remain before we stop waiting and renew. */
export const REFRESH_WHEN_REMAINING = 1 / 3

/**
 * Milliseconds from `nowMs` until the token should be renewed: the moment when
 * less than a third of its lifetime remains.
 *
 *   0     → renew now
 *   null  → do not renew (expired already, or the token carries no exp/iat)
 */
export function refreshDelayMs(token, nowMs = Date.now()) {
  const payload = decodeJwt(token)
  const exp = Number(payload?.exp)
  const iat = Number(payload?.iat)
  if (!Number.isFinite(exp) || !Number.isFinite(iat) || exp <= iat) return null
  const expMs = exp * 1000
  if (expMs <= nowMs) return null
  const lifetimeMs = (exp - iat) * 1000
  const refreshAt = expMs - lifetimeMs * REFRESH_WHEN_REMAINING
  return Math.max(0, Math.round(refreshAt - nowMs))
}
