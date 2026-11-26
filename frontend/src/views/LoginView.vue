<template>
  <div class="login-page">
    <div class="login-card">
      <h1 class="login-title">{{ $t('login.title') }}</h1>
      <p class="login-subtitle">{{ $t('login.subtitle') }}</p>

      <div class="tab-switcher" role="tablist" :aria-label="$t('login.modeLabel')">
        <button type="button" role="tab" :aria-selected="mode === 'login'" :class="{ active: mode === 'login' }" @click="setMode('login')">{{ $t('login.loginTab') }}</button>
        <button type="button" role="tab" :aria-selected="mode === 'register'" :class="{ active: mode === 'register' }" @click="setMode('register')">{{ $t('login.registerTab') }}</button>
      </div>

      <form @submit.prevent="submit" novalidate>
        <div v-if="mode === 'register'" class="field">
          <label for="login-fullname">{{ $t('login.fullName') }}</label>
          <input id="login-fullname" v-model="fullName" type="text" autocomplete="name" :placeholder="$t('login.fullNamePlaceholder')" />
        </div>
        <div class="field">
          <label for="login-email">{{ $t('login.email') }}</label>
          <input id="login-email" v-model.trim="email" type="email" autocomplete="email" :placeholder="$t('login.emailPlaceholder')" required />
        </div>
        <div class="field">
          <label for="login-password">{{ $t('login.password') }}</label>
          <input
            id="login-password"
            v-model="password"
            type="password"
            :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
            :placeholder="$t('login.passwordPlaceholder')"
            :aria-describedby="mode === 'register' ? 'login-password-hint' : undefined"
            required
          />
          <p v-if="mode === 'register'" id="login-password-hint" class="hint">{{ $t('login.passwordHint', { n: MIN_PASSWORD }) }}</p>
        </div>
        <div v-if="mode === 'register'" class="field">
          <label for="login-password2">{{ $t('login.confirmPassword') }}</label>
          <input id="login-password2" v-model="password2" type="password" autocomplete="new-password" :placeholder="$t('login.confirmPasswordPlaceholder')" required />
        </div>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <p v-if="lockedText" class="hint" role="status" aria-live="polite">{{ lockedText }}</p>
        <div v-if="unverifiedEmail" class="verify-box" role="status">
          <p><strong>{{ $t('verify.checkInbox') }}</strong></p>
          <p>{{ verifyMsg || $t('verify.checkInboxDesc', { email: unverifiedEmail }) }}</p>
          <button type="button" class="btn-link" :disabled="resending" @click="resendVerification">
            {{ resending ? $t('auth.sending') : $t('verify.resend') }}
          </button>
          <p v-if="resendMsg" class="hint">{{ resendMsg }}</p>
        </div>
        <button type="submit" class="btn-primary" :disabled="loading || (mode === 'login' && lockedFor > 0)">
          {{ loading ? $t('login.loading') : (mode === 'login' ? $t('login.loginButton') : $t('login.registerButton')) }}
        </button>
        <router-link v-if="mode === 'login'" to="/forgot-password" class="forgot-link">{{ $t('login.forgotPassword') }}</router-link>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import { apiError, apiErrorCode, retryAfterSeconds } from '../utils/apiError'
import { api } from '../api'
import { safeRedirect } from '../utils/http'

const MIN_PASSWORD = 8

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const { t } = useI18n()

const mode = ref('login')
const email = ref('')
const password = ref('')
const password2 = ref('')
const fullName = ref('')
const error = ref('')
const loading = ref(false)

// Set when the server requires a confirmed email address before login.
const unverifiedEmail = ref('')
const resending = ref(false)
const resendMsg = ref('')
const verifyMsg = ref('')

// Too many failed logins: the server says how long to wait (Retry-After).
const lockedFor = ref(0)
let lockTimer = null
const lockedText = computed(() => {
  const s = lockedFor.value
  if (s <= 0) return ''
  return s >= 90 ? t('login.lockedMinutes', { n: Math.ceil(s / 60) }) : t('login.lockedSeconds', { n: s })
})
function startLock(seconds) {
  clearInterval(lockTimer)
  lockedFor.value = seconds
  lockTimer = setInterval(() => {
    lockedFor.value -= 1
    if (lockedFor.value <= 0) { clearInterval(lockTimer); lockTimer = null; error.value = '' }
  }, 1000)
}
onBeforeUnmount(() => clearInterval(lockTimer))

function setMode(m) {
  mode.value = m
  error.value = ''
  unverifiedEmail.value = ''
  resendMsg.value = ''
}

async function resendVerification() {
  resending.value = true
  resendMsg.value = ''
  try {
    await api.auth.resendVerification({ email: unverifiedEmail.value })
    resendMsg.value = t('verify.resent')
  } catch (e) {
    resendMsg.value = apiError(e, t('verify.resendFailed'))
  } finally {
    resending.value = false
  }
}

function validate() {
  if (!email.value || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.value)) return t('login.invalidEmail')
  if (!password.value) return t('login.passwordRequired')
  if (mode.value === 'register') {
    if (password.value.length < MIN_PASSWORD) return t('login.passwordTooShort', { n: MIN_PASSWORD })
    if (password.value !== password2.value) return t('auth.passwordsMismatch')
  }
  return ''
}

async function submit() {
  error.value = validate()
  if (error.value) return
  unverifiedEmail.value = ''
  resendMsg.value = ''
  verifyMsg.value = ''
  loading.value = true
  try {
    if (mode.value === 'login') {
      await auth.login(email.value, password.value)
    } else {
      const res = await auth.register(email.value, password.value, fullName.value)
      if (res?.verificationRequired) {
        // Account created, but the address must be confirmed before the first login.
        unverifiedEmail.value = email.value
        verifyMsg.value = res.message
        mode.value = 'login'
        password.value = ''
        password2.value = ''
        return
      }
    }
    router.push(safeRedirect(route.query.redirect))
  } catch (e) {
    if (apiErrorCode(e) === 'EMAIL_NOT_VERIFIED') {
      // Account exists (or was just created) but its address is not confirmed yet.
      apiError(e)
      unverifiedEmail.value = email.value
      mode.value = 'login'
      password2.value = ''
      return
    }
    const wait = e?.response?.status === 429 ? retryAfterSeconds(e) : 0
    // The server's own words ("Invalid email or password", "Registration is disabled",
    // "Too many attempts"…)
    error.value = apiError(e, t('login.error'))
    if (wait > 0) startLock(wait)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.verify-box {
  border: 1px solid var(--info);
  background: var(--info-bg);
  color: var(--text-body);
  border-radius: 6px;
  padding: 0.75rem 0.9rem;
  margin-bottom: 0.9rem;
  font-size: 0.85rem;
}
.verify-box p { margin: 0 0 0.35rem; }
.btn-link {
  background: none;
  border: none;
  padding: 0;
  color: var(--accent);
  cursor: pointer;
  font-size: 0.85rem;
  text-decoration: underline;
}
.btn-link:disabled { opacity: 0.6; cursor: not-allowed; }

.login-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 80vh;
}

.login-card {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 2.5rem;
  width: 100%;
  max-width: 400px;
  box-shadow: var(--shadow-card);
}

.login-title {
  text-align: center;
  color: var(--text-primary);
  font-size: 1.75rem;
  margin-bottom: 0.25rem;
}

.login-subtitle {
  text-align: center;
  color: var(--text-muted);
  font-size: 0.9rem;
  margin-bottom: 1.5rem;
}

.tab-switcher {
  display: flex;
  gap: 0;
  margin-bottom: 1.5rem;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--border-light);
}

.tab-switcher button {
  flex: 1;
  padding: 0.6rem;
  border: none;
  background: var(--bg-tab-switcher);
  color: var(--text-muted);
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.2s;
}

.tab-switcher button.active {
  background: var(--accent);
  color: var(--accent-text);
}

.field {
  margin-bottom: 1rem;
}

.field label {
  display: block;
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 0.3rem;
}

.field input {
  width: 100%;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--border-light);
  border-radius: 6px;
  font-size: 0.9rem;
  transition: border-color 0.2s;
  background: var(--bg-input);
  color: var(--text-body);
}

.field input:focus {
  border-color: var(--brand);
}

.error {
  color: var(--danger);
  font-size: 0.85rem;
  margin-bottom: 0.75rem;
}

.btn-primary {
  width: 100%;
  padding: 0.7rem;
  background: var(--accent);
  color: var(--accent-text);
  border: none;
  border-radius: 6px;
  font-size: 0.95rem;
  cursor: pointer;
  transition: background 0.2s;
  margin-top: 0.5rem;
}

.btn-primary:hover {
  background: var(--accent-hover);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.forgot-link {
  display: block;
  text-align: center;
  margin-top: 0.75rem;
  font-size: 0.85rem;
  color: var(--text-muted);
  text-decoration: none;
}
.forgot-link:hover {
  color: var(--accent);
}
.hint {
  font-size: 0.78rem;
  color: var(--text-muted);
  margin-top: 0.25rem;
}
</style>
