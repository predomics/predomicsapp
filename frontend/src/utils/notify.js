/**
 * Browser notification utility for job status updates.
 * Uses the Notification API with localStorage permission tracking.
 */

const PERM_KEY = 'predomics_notifications'

/** Check if browser notifications are supported and enabled. */
export function isSupported() {
  return 'Notification' in window
}

/** Request permission if not already granted/denied. Returns true if granted. */
export async function requestPermission() {
  if (!isSupported()) return false

  // Respect user opt-out
  if (localStorage.getItem(PERM_KEY) === 'denied') return false

  if (Notification.permission === 'granted') return true
  if (Notification.permission === 'denied') return false

  const result = await Notification.requestPermission()
  if (result === 'denied') {
    localStorage.setItem(PERM_KEY, 'denied')
  }
  return result === 'granted'
}

/** Send a browser notification. */
export function notify(title, body, { tag = 'predomics', onClick } = {}) {
  if (!isSupported() || Notification.permission !== 'granted') return null

  const n = new Notification(title, {
    body,
    tag,
    icon: '/logo-dark.png',
  })

  if (onClick) {
    n.onclick = () => {
      window.focus()
      onClick()
      n.close()
    }
  }

  // Auto-close after 10 seconds
  setTimeout(() => n.close(), 10000)
  return n
}

/** Notify that a job completed. */
export function notifyJobCompleted(projectName, { auc, k, jobId } = {}) {
  let body = `Analysis finished for "${projectName}".`
  if (auc != null) {
    body += ` Best AUC: ${Number(auc).toFixed(4)}`
    if (k != null) body += ` (k=${k})`
  }
  return notify('Job Completed', body, {
    tag: `job-${jobId || 'done'}`,
    onClick: () => window.focus(),
  })
}

/** Notify that a job failed. */
export function notifyJobFailed(projectName, { jobId } = {}) {
  return notify('Job Failed', `Analysis failed for "${projectName}". Check the console for details.`, {
    tag: `job-${jobId || 'fail'}`,
    onClick: () => window.focus(),
  })
}
