import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'
import { api } from '../api'
import { refreshDelayMs } from '../utils/session'

/** setTimeout cannot wait longer than this (2^31-1 ms). */
const MAX_TIMER_MS = 2147483647

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const user = ref(null)

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.is_admin === true)

  // Set axios default header whenever token changes
  function setToken(t) {
    token.value = t
    if (t) {
      localStorage.setItem('token', t)
      axios.defaults.headers.common['Authorization'] = `Bearer ${t}`
    } else {
      localStorage.removeItem('token')
      delete axios.defaults.headers.common['Authorization']
    }
    scheduleRefresh()
  }

  // Restore token on app load
  if (token.value) {
    axios.defaults.headers.common['Authorization'] = `Bearer ${token.value}`
  }

  // ── Session renewal ──────────────────────────────────────────────────────
  // The access token is renewed when less than a third of its lifetime is left,
  // so an active user is never logged out mid-work. Servers without the
  // /auth/refresh endpoint answer 404: we then stop asking and the session
  // simply ends at expiry, as before.
  let refreshTimer = null
  let refreshSupported = true
  let refreshing = null

  function scheduleRefresh() {
    if (refreshTimer) { clearTimeout(refreshTimer); refreshTimer = null }
    if (!token.value || !refreshSupported) return
    const delay = refreshDelayMs(token.value)
    if (delay === null) return
    refreshTimer = setTimeout(refreshSession, Math.min(Math.max(delay, 1000), MAX_TIMER_MS))
  }

  async function refreshSession() {
    if (!token.value || !refreshSupported) return false
    if (refreshing) return refreshing
    const used = token.value
    refreshing = (async () => {
      try {
        const { data } = await api.auth.refresh(null, { silentError: true })
        // The user may have logged out or logged in again while we waited.
        if (data?.access_token && token.value === used) setToken(data.access_token)
        return true
      } catch (e) {
        const status = e?.response?.status
        if (status === 404 || status === 405) refreshSupported = false
        // 401 is handled by the http interceptor (session expired); anything
        // else (network blip, 5xx) is retried in a minute while the token lasts.
        else if (status !== 401) {
          refreshTimer = setTimeout(refreshSession, 60000)
        }
        return false
      } finally {
        refreshing = null
      }
    })()
    return refreshing
  }

  /** Timers are throttled in background tabs: re-check when the tab is shown again. */
  function onVisible() {
    if (typeof document !== 'undefined' && document.visibilityState === 'visible' && token.value) {
      const delay = refreshDelayMs(token.value)
      if (delay === 0) refreshSession()
      else scheduleRefresh()
    }
  }
  if (typeof document !== 'undefined') document.addEventListener('visibilitychange', onVisible)
  scheduleRefresh()

  async function login(email, password) {
    const { data } = await api.auth.login({ email, password })
    setToken(data.access_token)
    await fetchUser()
  }

  async function register(email, password, full_name) {
    const { data } = await api.auth.register({ email, password, full_name })
    // When the server requires a confirmed address, the account exists but
    // cannot log in yet: hand the server's message back instead of logging in.
    if (data?.verification_required) {
      return { verificationRequired: true, message: data.message || '' }
    }
    await login(email, password)
    return { verificationRequired: false }
  }

  async function fetchUser() {
    try {
      const { data } = await api.auth.me({ silentError: true })
      user.value = data
    } catch (e) {
      // Only an explicit rejection of the token ends the session; a network
      // blip or a 5xx must not log the user out.
      const status = e?.response?.status
      if (status === 401 || status === 403) logout()
    }
  }

  function logout() {
    setToken('')
    user.value = null
  }

  async function updateProfile(full_name) {
    const { data } = await api.auth.updateMe({ full_name })
    user.value = data
  }

  async function changePassword(current_password, new_password) {
    const { data } = await api.auth.changePassword({ current_password, new_password })
    // Changing the password invalidates every earlier token, including the one
    // in use: the server hands back a fresh one for this session.
    if (data?.access_token) setToken(data.access_token)
  }

  /** Storage used by this account: { used_bytes, quota_bytes } (quota 0 = unlimited), or null if the server has no quota endpoint. */
  async function fetchUsage() {
    try {
      const { data } = await api.auth.usage({ silentError: true })
      return data && typeof data.used_bytes === 'number' ? data : null
    } catch {
      return null
    }
  }

  /** One-time ticket for opening a WebSocket, or null when the server has none (fall back to polling). */
  async function wsTicket() {
    try {
      const { data } = await api.auth.wsTicket(null, { silentError: true })
      return data?.ticket || null
    } catch {
      return null
    }
  }

  async function searchUsers(query) {
    if (!query || query.trim().length < 3) return []  // the server needs 3 characters
    const { data } = await api.auth.searchUsers({ params: { q: query } })
    return data
  }

  return { token, user, isLoggedIn, isAdmin, login, register, fetchUser, logout, updateProfile, changePassword, searchUsers, refreshSession, fetchUsage, wsTicket }
})
