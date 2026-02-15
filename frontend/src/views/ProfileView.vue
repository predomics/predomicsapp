<template>
  <div class="profile">
    <h2>Profile</h2>

    <section class="card">
      <h3>Account Info</h3>
      <div class="info-row">
        <span class="label">Email</span>
        <span class="value">{{ auth.user?.email }}</span>
      </div>
      <div class="info-row">
        <span class="label">Joined</span>
        <span class="value">{{ auth.user?.created_at ? new Date(auth.user.created_at).toLocaleDateString() : '' }}</span>
      </div>
    </section>

    <section class="card">
      <h3>Edit Name</h3>
      <form @submit.prevent="saveName">
        <div class="form-group">
          <label>Full Name</label>
          <input v-model="fullName" type="text" placeholder="Your name" />
        </div>
        <button type="submit" class="btn btn-primary" :disabled="savingName">
          {{ savingName ? 'Saving...' : 'Save' }}
        </button>
        <span v-if="nameMsg" class="msg success">{{ nameMsg }}</span>
      </form>
    </section>

    <section class="card">
      <h3>Preferences</h3>
      <div class="pref-row">
        <div>
          <span class="pref-label">Browser Notifications</span>
          <span class="pref-desc">Get notified when jobs complete or fail</span>
        </div>
        <button class="btn btn-small" @click="toggleNotifications">
          {{ notifStatus }}
        </button>
      </div>
      <div class="pref-row">
        <div>
          <span class="pref-label">Onboarding Tour</span>
          <span class="pref-desc">Show the welcome tour again on next visit</span>
        </div>
        <button class="btn btn-small" @click="resetTour">Reset Tour</button>
      </div>
      <span v-if="prefMsg" class="msg success">{{ prefMsg }}</span>
    </section>

    <section class="card">
      <h3>Change Password</h3>
      <form @submit.prevent="savePassword">
        <div class="form-group">
          <label>Current Password</label>
          <input v-model="currentPw" type="password" />
        </div>
        <div class="form-group">
          <label>New Password</label>
          <input v-model="newPw" type="password" />
        </div>
        <button type="submit" class="btn btn-primary" :disabled="savingPw || !currentPw || !newPw">
          {{ savingPw ? 'Saving...' : 'Change Password' }}
        </button>
        <span v-if="pwMsg" class="msg" :class="pwError ? 'error' : 'success'">{{ pwMsg }}</span>
      </form>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth'
import { isSupported, requestPermission } from '../utils/notify'

const auth = useAuthStore()

const fullName = ref('')
const savingName = ref(false)
const nameMsg = ref('')

const currentPw = ref('')
const newPw = ref('')
const savingPw = ref(false)
const pwMsg = ref('')
const pwError = ref(false)
const prefMsg = ref('')

const notifStatus = computed(() => {
  if (!isSupported()) return 'Not supported'
  if (localStorage.getItem('predomics_notifications') === 'denied') return 'Disabled'
  if (typeof Notification !== 'undefined' && Notification.permission === 'granted') return 'Enabled'
  if (typeof Notification !== 'undefined' && Notification.permission === 'denied') return 'Blocked'
  return 'Enable'
})

async function toggleNotifications() {
  if (!isSupported()) return
  if (localStorage.getItem('predomics_notifications') === 'denied') {
    localStorage.removeItem('predomics_notifications')
    await requestPermission()
    prefMsg.value = 'Notifications re-enabled'
  } else if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
    localStorage.setItem('predomics_notifications', 'denied')
    prefMsg.value = 'Notifications disabled'
  } else {
    const granted = await requestPermission()
    prefMsg.value = granted ? 'Notifications enabled' : 'Permission denied by browser'
  }
  setTimeout(() => { prefMsg.value = '' }, 3000)
}

function resetTour() {
  localStorage.removeItem('predomics_onboarding_dismissed')
  prefMsg.value = 'Tour will show on next page load'
  setTimeout(() => { prefMsg.value = '' }, 3000)
}

onMounted(() => {
  fullName.value = auth.user?.full_name || ''
})

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
</style>
