/** Job status helpers shared by the console, the job table and the dashboard. */
import i18n from '../i18n'

export const TERMINAL_STATUSES = ['completed', 'failed', 'cancelled']

/** The server has no "cancelled" status: a cancelled job is `failed` with this message. */
const CANCELLED_RE = /^cancell?ed by user/i
/** Jobs that were running when the server restarted are `failed` with a message naming the restart. */
const INTERRUPTED_RE = /server restart|interrupted/i

/** True for a job the user stopped (not an error). Accepts a job object or (status, message). */
export function isCancelled(job, message) {
  const status = typeof job === 'string' ? job : job?.status
  const msg = typeof job === 'string' ? message : job?.error_message
  if (status === 'cancelled') return true
  return status === 'failed' && CANCELLED_RE.test(String(msg || '').trim())
}

/** True for a job cut short by a server restart. */
export function isInterrupted(job) {
  return job?.status === 'failed' && !isCancelled(job) && INTERRUPTED_RE.test(String(job?.error_message || ''))
}

/**
 * Status to show: what the server says, except that a user-cancelled job reads
 * "cancelled" instead of "failed".
 */
export function displayStatus(job) {
  if (!job) return ''
  return isCancelled(job) ? 'cancelled' : job.status
}

export function isLive(status) {
  return status === 'pending' || status === 'running'
}

/** Translated label for a job status (falls back to the raw value). */
export function statusLabel(status) {
  if (!status) return ''
  const key = `common.${status}`
  return i18n.global.te(key) ? i18n.global.t(key) : status
}

/** Text glyph so status is never conveyed by colour alone. */
export function statusGlyph(status) {
  return { completed: '✓', failed: '✗', running: '▶', pending: '…', cancelled: '■' }[status] || ''
}

/** Job list as the UI shows it: user-cancelled jobs carry status "cancelled". */
export function normalizeJobs(list) {
  if (!Array.isArray(list)) return []
  return list.map((j) => (j && typeof j === 'object' && j.status !== 'cancelled' && isCancelled(j) ? { ...j, status: 'cancelled' } : j))
}
