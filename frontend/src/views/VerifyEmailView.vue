<template>
  <div class="verify-page">
    <div class="verify-card">
      <h1>{{ $t('verify.title') }}</h1>

      <p v-if="state === 'checking'" role="status">{{ $t('verify.checking') }}</p>

      <div v-else-if="state === 'done'" role="status">
        <p class="ok"><span aria-hidden="true">✓</span> {{ $t('verify.done') }}</p>
        <router-link to="/login" class="btn-primary as-link">{{ $t('verify.goToLogin') }}</router-link>
      </div>

      <div v-else>
        <p class="error" role="alert">{{ error || $t('verify.missingToken') }}</p>
        <form @submit.prevent="resend" novalidate>
          <div class="field">
            <label for="verify-email">{{ $t('auth.email') }}</label>
            <input id="verify-email" v-model.trim="email" type="email" autocomplete="email" :placeholder="$t('auth.emailPlaceholder')" required />
          </div>
          <button type="submit" class="btn-primary" :disabled="sending || !email">
            {{ sending ? $t('auth.sending') : $t('verify.resend') }}
          </button>
          <p v-if="resendMsg" class="hint" role="status">{{ resendMsg }}</p>
        </form>
        <router-link to="/login" class="back-link">{{ $t('auth.backToLogin') }}</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { apiError } from '../utils/apiError'

const route = useRoute()
const { t } = useI18n()

const state = ref('checking') // checking | done | failed
const error = ref('')
const email = ref(typeof route.query.email === 'string' ? route.query.email : '')
const sending = ref(false)
const resendMsg = ref('')

onMounted(async () => {
  const token = typeof route.query.token === 'string' ? route.query.token : ''
  if (!token) { state.value = 'failed'; return }
  try {
    await api.auth.verifyEmail({ token })
    state.value = 'done'
  } catch (e) {
    error.value = apiError(e, t('verify.failed'))
    state.value = 'failed'
  }
})

async function resend() {
  if (!email.value) return
  sending.value = true
  resendMsg.value = ''
  try {
    await api.auth.resendVerification({ email: email.value })
    resendMsg.value = t('verify.resent')
  } catch (e) {
    resendMsg.value = apiError(e, t('verify.resendFailed'))
  } finally {
    sending.value = false
  }
}
</script>

<style scoped>
.verify-page { display: flex; justify-content: center; align-items: center; min-height: 80vh; }
.verify-card {
  background: var(--bg-card); border-radius: 12px; padding: 2.5rem;
  width: 100%; max-width: 420px; box-shadow: var(--shadow-card);
}
.verify-card h1 { text-align: center; color: var(--text-primary); font-size: 1.5rem; margin-bottom: 1rem; }
.verify-card p { color: var(--text-body); font-size: 0.9rem; margin-bottom: 1rem; }
.ok { color: var(--success-dark); font-weight: 600; }
.error { color: var(--danger); }
.hint { color: var(--text-secondary); font-size: 0.85rem; margin-top: 0.75rem; }
.field { margin-bottom: 1rem; }
.field label { display: block; font-size: 0.85rem; font-weight: 500; color: var(--text-secondary); margin-bottom: 0.3rem; }
.field input {
  width: 100%; padding: 0.6rem 0.75rem; border: 1px solid var(--border-light); border-radius: 6px;
  font-size: 0.9rem; background: var(--bg-input); color: var(--text-body);
}
.btn-primary {
  display: block; width: 100%; padding: 0.7rem; background: var(--accent); color: var(--accent-text);
  border: none; border-radius: 6px; font-size: 0.95rem; cursor: pointer; text-align: center; text-decoration: none;
}
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.back-link { display: block; text-align: center; margin-top: 1rem; font-size: 0.85rem; color: var(--accent); }
</style>
