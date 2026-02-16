<template>
  <div class="profile">
    <h2>{{ $t('profile.title') }}</h2>

    <section class="card">
      <h3>{{ $t('profile.accountInfo') }}</h3>
      <div class="info-row">
        <span class="label">{{ $t('profile.email') }}</span>
        <span class="value">{{ auth.user?.email }}</span>
      </div>
      <div class="info-row">
        <span class="label">{{ $t('profile.joined') }}</span>
        <span class="value">{{ auth.user?.created_at ? new Date(auth.user.created_at).toLocaleDateString() : '' }}</span>
      </div>
    </section>

    <section class="card">
      <h3>{{ $t('profile.editName') }}</h3>
      <form @submit.prevent="saveName">
        <div class="form-group">
          <label>{{ $t('profile.fullName') }}</label>
          <input v-model="fullName" type="text" :placeholder="$t('profile.yourName')" />
        </div>
        <button type="submit" class="btn btn-primary" :disabled="savingName">
          {{ savingName ? $t('profile.saving') : $t('profile.save') }}
        </button>
        <span v-if="nameMsg" class="msg success">{{ nameMsg }}</span>
      </form>
    </section>

    <section class="card">
      <h3>{{ $t('profile.preferences') }}</h3>
      <div class="pref-row">
        <div>
          <span class="pref-label">{{ $t('profile.browserNotifications') }}</span>
          <span class="pref-desc">{{ $t('profile.notifDesc') }}</span>
        </div>
        <button class="btn btn-small" @click="toggleNotifications">
          {{ notifStatus }}
        </button>
      </div>
      <div class="pref-row">
        <div>
          <span class="pref-label">{{ $t('profile.onboardingTour') }}</span>
          <span class="pref-desc">{{ $t('profile.tourDesc') }}</span>
        </div>
        <button class="btn btn-small" @click="resetTour">{{ $t('profile.resetTour') }}</button>
      </div>
      <span v-if="prefMsg" class="msg success">{{ prefMsg }}</span>
    </section>

    <!-- API Keys Section -->
    <section class="card">
      <h3>{{ $t('profile.apiKeys') }}</h3>
      <p class="card-desc">{{ $t('profile.apiKeysDesc') }}</p>

      <div class="api-key-create">
        <input v-model="apiKeyName" :placeholder="$t('profile.keyNamePlaceholder')" class="form-input" @keyup.enter="createApiKey" />
        <button class="btn btn-primary" @click="createApiKey" :disabled="!apiKeyName.trim() || creatingKey">
          {{ creatingKey ? $t('profile.creating') : $t('profile.createKey') }}
        </button>
      </div>

      <div v-if="newKeySecret" class="new-key-alert">
        <strong>{{ $t('profile.copyKeyNow') }}</strong>
        <code>{{ newKeySecret }}</code>
      </div>

      <div v-if="apiKeys.length > 0" class="key-list">
        <div v-for="k in apiKeys" :key="k.id" class="key-row">
          <div>
            <span class="key-name">{{ k.name }}</span>
            <span class="key-prefix">{{ k.prefix }}...</span>
            <span v-if="k.last_used_at" class="key-used">{{ $t('profile.lastUsed') }} {{ new Date(k.last_used_at).toLocaleDateString() }}</span>
          </div>
          <button class="btn-danger-sm" @click="revokeApiKey(k)">{{ $t('profile.revoke') }}</button>
        </div>
      </div>
      <div v-else class="empty-hint">{{ $t('profile.noApiKeys') }}</div>
    </section>

    <!-- Webhooks Section -->
    <section class="card">
      <h3>{{ $t('profile.webhooks') }}</h3>
      <p class="card-desc">{{ $t('profile.webhooksDesc') }}</p>

      <div class="webhook-create">
        <input v-model="webhookName" :placeholder="$t('profile.webhookName')" class="form-input" />
        <input v-model="webhookUrl" :placeholder="$t('profile.webhookUrlPlaceholder')" class="form-input flex-1" />
        <button class="btn btn-primary" @click="createWebhook" :disabled="!webhookName.trim() || !webhookUrl.trim() || creatingWebhook">
          {{ creatingWebhook ? $t('profile.creating') : $t('profile.addWebhook') }}
        </button>
      </div>

      <div v-if="newWebhookSecret" class="new-key-alert">
        <strong>{{ $t('profile.webhookSecret') }}</strong>
        <code>{{ newWebhookSecret }}</code>
      </div>

      <div v-if="webhooks.length > 0" class="key-list">
        <div v-for="w in webhooks" :key="w.id" class="key-row">
          <div>
            <span class="key-name">{{ w.name }}</span>
            <span class="key-prefix">{{ w.url }}</span>
            <span class="key-used">{{ $t('profile.events') }} {{ w.events?.join(', ') }}</span>
          </div>
          <div class="key-actions">
            <button class="btn-test-sm" @click="testWebhook(w)">{{ $t('profile.test') }}</button>
            <button class="btn-danger-sm" @click="deleteWebhook(w)">{{ $t('profile.deleteWebhook') }}</button>
          </div>
        </div>
      </div>
      <div v-else class="empty-hint">{{ $t('profile.noWebhooks') }}</div>
      <span v-if="webhookMsg" class="msg" :class="webhookMsgType">{{ webhookMsg }}</span>
    </section>

    <section class="card">
      <h3>{{ $t('profile.changePassword') }}</h3>
      <form @submit.prevent="savePassword">
        <div class="form-group">
          <label>{{ $t('profile.currentPassword') }}</label>
          <input v-model="currentPw" type="password" />
        </div>
        <div class="form-group">
          <label>{{ $t('profile.newPassword') }}</label>
          <input v-model="newPw" type="password" />
        </div>
        <button type="submit" class="btn btn-primary" :disabled="savingPw || !currentPw || !newPw">
          {{ savingPw ? $t('profile.saving') : $t('profile.changePasswordBtn') }}
        </button>
        <span v-if="pwMsg" class="msg" :class="pwError ? 'error' : 'success'">{{ pwMsg }}</span>
      </form>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import { useAuthStore } from '../stores/auth'
import { isSupported, requestPermission } from '../utils/notify'
import { useI18n } from 'vue-i18n'

const auth = useAuthStore()
const { t } = useI18n()

const fullName = ref('')
const savingName = ref(false)
const nameMsg = ref('')

const currentPw = ref('')
const newPw = ref('')
const savingPw = ref(false)
const pwMsg = ref('')
const pwError = ref(false)
const prefMsg = ref('')

// API Keys
const apiKeys = ref([])
const apiKeyName = ref('')
const creatingKey = ref(false)
const newKeySecret = ref('')

// Webhooks
const webhooks = ref([])
const webhookName = ref('')
const webhookUrl = ref('')
const creatingWebhook = ref(false)
const newWebhookSecret = ref('')
const webhookMsg = ref('')
const webhookMsgType = ref('success')

const notifStatus = computed(() => {
  if (!isSupported()) return t('profile.notSupported')
  if (localStorage.getItem('predomics_notifications') === 'denied') return t('profile.disabled')
  if (typeof Notification !== 'undefined' && Notification.permission === 'granted') return t('profile.enabled')
  if (typeof Notification !== 'undefined' && Notification.permission === 'denied') return t('profile.blocked')
  return t('profile.enable')
})

async function toggleNotifications() {
  if (!isSupported()) return
  if (localStorage.getItem('predomics_notifications') === 'denied') {
    localStorage.removeItem('predomics_notifications')
    await requestPermission()
    prefMsg.value = t('profile.notifReEnabled')
  } else if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
    localStorage.setItem('predomics_notifications', 'denied')
    prefMsg.value = t('profile.notifDisabled')
  } else {
    const granted = await requestPermission()
    prefMsg.value = granted ? t('profile.notifEnabled') : t('profile.notifDenied')
  }
  setTimeout(() => { prefMsg.value = '' }, 3000)
}

function resetTour() {
  localStorage.removeItem('predomics_onboarding_dismissed')
  prefMsg.value = t('profile.tourReset')
  setTimeout(() => { prefMsg.value = '' }, 3000)
}

onMounted(() => {
  fullName.value = auth.user?.full_name || ''
  fetchApiKeys()
  fetchWebhooks()
})

// API Key functions
async function fetchApiKeys() {
  try {
    const { data } = await axios.get('/api/auth/api-keys')
    apiKeys.value = data
  } catch { /* ignore */ }
}

async function createApiKey() {
  if (!apiKeyName.value.trim()) return
  creatingKey.value = true
  newKeySecret.value = ''
  try {
    const { data } = await axios.post('/api/auth/api-keys', { name: apiKeyName.value.trim() })
    newKeySecret.value = data.key
    apiKeyName.value = ''
    await fetchApiKeys()
  } catch (e) {
    alert(e.response?.data?.detail || 'Failed to create key')
  } finally {
    creatingKey.value = false
  }
}

async function revokeApiKey(k) {
  if (!confirm(`Revoke API key "${k.name}"? This cannot be undone.`)) return
  try {
    await axios.delete(`/api/auth/api-keys/${k.id}`)
    apiKeys.value = apiKeys.value.filter(x => x.id !== k.id)
  } catch (e) {
    alert(e.response?.data?.detail || 'Failed to revoke key')
  }
}

// Webhook functions
async function fetchWebhooks() {
  try {
    const { data } = await axios.get('/api/webhooks/')
    webhooks.value = data
  } catch { /* ignore */ }
}

async function createWebhook() {
  if (!webhookName.value.trim() || !webhookUrl.value.trim()) return
  creatingWebhook.value = true
  newWebhookSecret.value = ''
  try {
    const { data } = await axios.post('/api/webhooks/', {
      name: webhookName.value.trim(),
      url: webhookUrl.value.trim(),
    })
    newWebhookSecret.value = data.secret
    webhookName.value = ''
    webhookUrl.value = ''
    await fetchWebhooks()
  } catch (e) {
    alert(e.response?.data?.detail || 'Failed to create webhook')
  } finally {
    creatingWebhook.value = false
  }
}

async function testWebhook(w) {
  webhookMsg.value = ''
  try {
    const { data } = await axios.post(`/api/webhooks/${w.id}/test`)
    webhookMsg.value = `Test ${data.status}`
    webhookMsgType.value = data.status === 'delivered' ? 'success' : 'error'
  } catch (e) {
    webhookMsg.value = e.response?.data?.detail || 'Test failed'
    webhookMsgType.value = 'error'
  }
  setTimeout(() => { webhookMsg.value = '' }, 4000)
}

async function deleteWebhook(w) {
  if (!confirm(`Delete webhook "${w.name}"?`)) return
  try {
    await axios.delete(`/api/webhooks/${w.id}`)
    webhooks.value = webhooks.value.filter(x => x.id !== w.id)
  } catch (e) {
    alert(e.response?.data?.detail || 'Failed to delete webhook')
  }
}

async function saveName() {
  savingName.value = true
  nameMsg.value = ''
  try {
    await auth.updateProfile(fullName.value)
    nameMsg.value = 'Name updated'
  } catch (e) {
    nameMsg.value = e.response?.data?.detail || 'Failed to update'
  } finally {
    savingName.value = false
  }
}

async function savePassword() {
  savingPw.value = true
  pwMsg.value = ''
  pwError.value = false
  try {
    await auth.changePassword(currentPw.value, newPw.value)
    pwMsg.value = 'Password changed'
    currentPw.value = ''
    newPw.value = ''
  } catch (e) {
    pwError.value = true
    pwMsg.value = e.response?.data?.detail || 'Failed to change password'
  } finally {
    savingPw.value = false
  }
}
</script>

<style scoped>
.profile {
  max-width: 500px;
  margin: 0 auto;
}

.profile h2 {
  margin-bottom: 1.5rem;
  color: var(--text-primary);
}

.card {
  background: var(--bg-card);
  padding: 1.5rem;
  border-radius: 8px;
  box-shadow: var(--shadow);
  margin-bottom: 1.5rem;
}

.card h3 {
  margin-bottom: 1rem;
  color: var(--text-primary);
  font-size: 1rem;
}

.info-row {
  display: flex;
  justify-content: space-between;
  padding: 0.4rem 0;
  border-bottom: 1px solid var(--border-lighter);
  font-size: 0.9rem;
}

.info-row .label { color: var(--text-muted); }
.info-row .value { color: var(--text-body); font-weight: 500; }

.form-group {
  margin-bottom: 0.75rem;
}

.form-group label {
  display: block;
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin-bottom: 0.25rem;
}

.form-group input {
  width: 100%;
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 0.9rem;
  background: var(--bg-input);
  color: var(--text-body);
}

.btn {
  padding: 0.5rem 1.25rem;
  border: none;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
}

.btn-primary {
  background: var(--accent);
  color: var(--accent-text);
}

.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.msg {
  margin-left: 0.75rem;
  font-size: 0.8rem;
}

.msg.success { color: var(--success); }
.msg.error { color: var(--danger); }

.pref-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border-lighter);
}
.pref-row:last-of-type { border-bottom: none; }
.pref-label { display: block; font-size: 0.88rem; color: var(--text-body); }
.pref-desc { display: block; font-size: 0.75rem; color: var(--text-muted); }
.btn-small {
  padding: 0.3rem 0.8rem;
  background: var(--bg-badge);
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 0.78rem;
  color: var(--text-secondary);
  cursor: pointer;
  white-space: nowrap;
}
.btn-small:hover { border-color: var(--accent); color: var(--accent); }

/* API Keys & Webhooks */
.card-desc {
  font-size: 0.82rem;
  color: var(--text-muted);
  margin-bottom: 0.75rem;
}
.api-key-create, .webhook-create {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
}
.form-input {
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 0.85rem;
  background: var(--bg-input);
  color: var(--text-body);
  min-width: 160px;
}
.flex-1 { flex: 1; }
.new-key-alert {
  padding: 0.6rem 0.75rem;
  background: var(--warning-bg, #fff3e0);
  border: 1px solid var(--warning, #ff9800);
  border-radius: 6px;
  font-size: 0.8rem;
  margin-bottom: 0.75rem;
  word-break: break-all;
}
.new-key-alert code {
  display: block;
  margin-top: 0.35rem;
  font-size: 0.75rem;
  color: var(--text-primary);
}
.key-list {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.key-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.4rem 0.5rem;
  background: var(--bg-badge);
  border-radius: 4px;
  font-size: 0.82rem;
}
.key-name {
  font-weight: 600;
  color: var(--text-body);
  margin-right: 0.5rem;
}
.key-prefix {
  color: var(--text-muted);
  font-family: monospace;
  font-size: 0.75rem;
  margin-right: 0.5rem;
}
.key-used {
  font-size: 0.72rem;
  color: var(--text-faint);
}
.key-actions {
  display: flex;
  gap: 0.35rem;
}
.btn-danger-sm {
  padding: 0.2rem 0.5rem;
  border: 1px solid var(--danger);
  color: var(--danger);
  background: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.72rem;
}
.btn-danger-sm:hover { background: var(--danger-bg); }
.btn-test-sm {
  padding: 0.2rem 0.5rem;
  border: 1px solid var(--accent);
  color: var(--accent);
  background: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.72rem;
}
.btn-test-sm:hover { background: var(--accent-faint, rgba(59,130,246,0.08)); }
.empty-hint {
  font-size: 0.82rem;
  color: var(--text-faint);
  padding: 0.5rem 0;
}
</style>
