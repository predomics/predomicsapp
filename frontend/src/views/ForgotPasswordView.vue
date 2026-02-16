<template>
  <div class="forgot-page">
    <div class="forgot-card">
      <h1>{{ $t('auth.resetPassword') }}</h1>
      <p class="subtitle">{{ $t('auth.resetDesc') }}</p>

      <form @submit.prevent="submit" v-if="!sent">
        <div class="field">
          <label>{{ $t('auth.email') }}</label>
          <input v-model="email" type="email" :placeholder="$t('auth.emailPlaceholder')" required />
        </div>
        <p v-if="error" class="error">{{ error }}</p>
        <button type="submit" class="btn-primary" :disabled="loading">
          {{ loading ? $t('auth.sending') : $t('auth.sendResetLink') }}
        </button>
      </form>

      <div v-else class="success-msg">
        <p>{{ $t('auth.emailSentMsg') }}</p>
        <p v-if="devToken" class="dev-token">
          {{ $t('auth.devModeMsg') }}<br/>
          <code>{{ devToken }}</code>
          <br/>
          <router-link :to="`/reset-password?token=${devToken}`">{{ $t('auth.resetNow') }}</router-link>
        </p>
      </div>

      <router-link to="/login" class="back-link">{{ $t('auth.backToLogin') }}</router-link>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'

const { t } = useI18n()

const email = ref('')
const loading = ref(false)
const error = ref('')
const sent = ref(false)
const devToken = ref('')

async function submit() {
  error.value = ''
  loading.value = true
  try {
    const { data } = await axios.post('/api/auth/forgot-password', { email: email.value })
    sent.value = true
    // In dev mode (no SMTP), the token is returned directly
    if (data.token) devToken.value = data.token
  } catch (e) {
    error.value = e.response?.data?.detail || 'Something went wrong'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.forgot-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 80vh;
}
.forgot-card {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 2.5rem;
  width: 100%;
  max-width: 400px;
  box-shadow: var(--shadow-card);
}
.forgot-card h1 {
  text-align: center;
  color: var(--text-primary);
  font-size: 1.5rem;
  margin-bottom: 0.25rem;
}
.subtitle {
  text-align: center;
  color: var(--text-muted);
  font-size: 0.88rem;
  margin-bottom: 1.5rem;
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
  background: var(--bg-input);
  color: var(--text-body);
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
}
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.success-msg {
  text-align: center;
  color: var(--text-body);
  font-size: 0.9rem;
  line-height: 1.5;
}
.dev-token {
  margin-top: 1rem;
  padding: 0.75rem;
  background: var(--bg-badge);
  border-radius: 6px;
  font-size: 0.8rem;
  word-break: break-all;
}
.dev-token code {
  color: var(--accent);
  font-size: 0.75rem;
}
.back-link {
  display: block;
  text-align: center;
  margin-top: 1.25rem;
  font-size: 0.85rem;
  color: var(--text-muted);
  text-decoration: none;
}
.back-link:hover { color: var(--accent); }
</style>
