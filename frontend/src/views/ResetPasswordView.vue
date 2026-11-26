<template>
  <div class="reset-page">
    <div class="reset-card">
      <h1>{{ $t('auth.setNewPassword') }}</h1>

      <div v-if="!token" class="error-msg">
        <p>{{ $t('auth.missingToken') }}</p>
        <router-link to="/forgot-password" class="back-link">{{ $t('auth.requestNewLink') }}</router-link>
      </div>

      <form v-else-if="!done" @submit.prevent="submit">
        <div class="field">
          <label for="reset-password">{{ $t('auth.newPassword') }}</label>
          <input id="reset-password" v-model="password" type="password" autocomplete="new-password" :placeholder="$t('auth.newPasswordPlaceholder')" required :minlength="MIN_PASSWORD" aria-describedby="reset-password-hint" />
          <p id="reset-password-hint" class="hint">{{ $t('login.passwordHint', { n: MIN_PASSWORD }) }}</p>
        </div>
        <div class="field">
          <label for="reset-password2">{{ $t('auth.confirmPassword') }}</label>
          <input id="reset-password2" v-model="confirm" type="password" autocomplete="new-password" :placeholder="$t('login.confirmPasswordPlaceholder')" required />
        </div>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button type="submit" class="btn-primary" :disabled="loading">
          {{ loading ? $t('auth.resetting') : $t('auth.resetBtn') }}
        </button>
      </form>

      <div v-else class="success-msg">
        <p>{{ $t('auth.resetSuccess') }}</p>
        <router-link to="/login" class="btn-primary" style="display:inline-block;margin-top:1rem;text-align:center;text-decoration:none;">
          {{ $t('auth.goToLogin') }}
        </router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { apiError } from '../utils/apiError'

const MIN_PASSWORD = 8

const { t } = useI18n()

const route = useRoute()
const token = ref(route.query.token || '')
const password = ref('')
const confirm = ref('')
const loading = ref(false)
const error = ref('')
const done = ref(false)

async function submit() {
  if (password.value.length < MIN_PASSWORD) {
    error.value = t('login.passwordTooShort', { n: MIN_PASSWORD })
    return
  }
  if (password.value !== confirm.value) {
    error.value = t('auth.passwordsMismatch')
    return
  }
  error.value = ''
  loading.value = true
  try {
    await api.auth.resetPassword({
      token: token.value,
      new_password: password.value,
    })
    done.value = true
  } catch (e) {
    error.value = apiError(e, t('auth.resetFailed'))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.reset-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 80vh;
}
.reset-card {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 2.5rem;
  width: 100%;
  max-width: 400px;
  box-shadow: var(--shadow-card);
}
.reset-card h1 {
  text-align: center;
  color: var(--text-primary);
  font-size: 1.5rem;
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
.error-msg {
  text-align: center;
  color: var(--danger);
  font-size: 0.9rem;
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
  color: var(--success-dark, #2e7d32);
  font-size: 0.95rem;
}
.back-link {
  display: block;
  text-align: center;
  margin-top: 1rem;
  color: var(--accent);
  font-size: 0.85rem;
}
.hint {
  font-size: 0.78rem;
  color: var(--text-muted);
  margin-top: 0.25rem;
}
</style>
