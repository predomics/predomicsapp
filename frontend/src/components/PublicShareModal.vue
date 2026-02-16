<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <div class="modal-header">
        <h3>{{ $t('modals.publicShareLinks') }}</h3>
        <button class="close-btn" @click="$emit('close')">&times;</button>
      </div>

      <div class="modal-body">
        <p class="hint">{{ $t('modals.publicShareDesc') }}</p>

        <!-- Create new link -->
        <div class="create-row">
          <label class="expiry-label">
            {{ $t('modals.expiresIn') }}
            <select v-model="expiryDays">
              <option :value="null">{{ $t('modals.never') }}</option>
              <option :value="7">{{ $t('modals.days7') }}</option>
              <option :value="30">{{ $t('modals.days30') }}</option>
              <option :value="90">{{ $t('modals.days90') }}</option>
            </select>
          </label>
          <button class="btn btn-primary" @click="createLink" :disabled="creating">
            {{ creating ? $t('modals.creating') : $t('modals.createLink') }}
          </button>
        </div>

        <div v-if="copiedMsg" class="msg msg-success">{{ copiedMsg }}</div>

        <!-- Existing links -->
        <div v-if="links.length > 0" class="links-list">
          <div v-for="link in links" :key="link.id" class="link-row">
            <div class="link-url">
              <code>{{ buildUrl(link.token) }}</code>
              <button class="btn-sm btn-outline" @click="copyLink(link.token)">{{ $t('modals.copy') }}</button>
            </div>
            <div class="link-meta">
              <span>{{ $t('modals.created') }} {{ formatDate(link.created_at) }}</span>
              <span v-if="link.expires_at">{{ $t('modals.expires') }} {{ formatDate(link.expires_at) }}</span>
              <span v-else class="no-expiry">{{ $t('modals.noExpiry') }}</span>
              <button class="btn-sm btn-danger" @click="revokeLink(link.id)">{{ $t('modals.revoke') }}</button>
            </div>
          </div>
        </div>
        <div v-else-if="!loading" class="empty">{{ $t('modals.noPublicLinks') }}</div>
        <div v-if="loading" class="loading-msg">{{ $t('modals.loading') }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'

const { t } = useI18n()

const props = defineProps({
  projectId: String,
})
const emit = defineEmits(['close'])

const links = ref([])
const loading = ref(true)
const creating = ref(false)
const expiryDays = ref(null)
const copiedMsg = ref('')

async function loadLinks() {
  loading.value = true
  try {
    const { data } = await axios.get(`/api/projects/${props.projectId}/public`)
    links.value = data
  } catch (e) {
    console.error('Failed to load public links:', e)
  } finally {
    loading.value = false
  }
}

async function createLink() {
  creating.value = true
  try {
    const { data } = await axios.post(`/api/projects/${props.projectId}/public`, {
      expires_in_days: expiryDays.value,
    })
    links.value.unshift(data)
    await copyLink(data.token)
  } catch (e) {
    alert('Failed to create link: ' + (e.response?.data?.detail || e.message))
  } finally {
    creating.value = false
  }
}

async function revokeLink(id) {
  if (!confirm(t('modals.revokeConfirm'))) return
  try {
    await axios.delete(`/api/projects/${props.projectId}/public/${id}`)
    links.value = links.value.filter(l => l.id !== id)
  } catch (e) {
    alert('Failed to revoke: ' + (e.response?.data?.detail || e.message))
  }
}

function buildUrl(token) {
  return `${window.location.origin}/public/${token}`
}

async function copyLink(token) {
  const url = buildUrl(token)
  try {
    await navigator.clipboard.writeText(url)
    copiedMsg.value = t('modals.linkCopied')
    setTimeout(() => { copiedMsg.value = '' }, 3000)
  } catch {
    copiedMsg.value = ''
  }
}

function formatDate(isoStr) {
  if (!isoStr) return ''
  return new Date(isoStr).toLocaleDateString()
}

onMounted(loadLinks)
</script>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.modal {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 12px; width: 540px; max-width: 95vw;
  max-height: 80vh; overflow-y: auto; padding: 1.5rem;
}
.modal-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 1rem;
}
.modal-header h3 { margin: 0; font-size: 1.15rem; }
.close-btn {
  background: none; border: none; color: var(--text-muted);
  font-size: 1.5rem; cursor: pointer;
}
.close-btn:hover { color: var(--text-primary); }

.hint { color: var(--text-muted); font-size: 0.85rem; margin-bottom: 1rem; }

.create-row {
  display: flex; align-items: center; gap: 0.75rem;
  margin-bottom: 1rem;
}
.expiry-label {
  font-size: 0.85rem; color: var(--text-secondary);
  display: flex; align-items: center; gap: 0.4rem;
}
.expiry-label select {
  background: var(--bg-input); color: var(--text-body);
  border: 1px solid var(--border); border-radius: 4px;
  padding: 0.3rem 0.5rem; font-size: 0.8rem;
}

.btn { padding: 0.45rem 1rem; border-radius: 6px; border: none; cursor: pointer; font-size: 0.85rem; }
.btn-primary { background: var(--accent); color: var(--accent-text); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.msg { padding: 0.4rem 0.7rem; border-radius: 6px; font-size: 0.8rem; margin-bottom: 0.75rem; }
.msg-success { background: var(--success-bg); color: var(--success); }

.links-list { display: flex; flex-direction: column; gap: 0.75rem; }
.link-row {
  background: var(--bg-page); border: 1px solid var(--border-light);
  border-radius: 8px; padding: 0.75rem;
}
.link-url {
  display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.4rem;
}
.link-url code {
  font-size: 0.75rem; color: var(--accent);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;
}
.link-meta {
  display: flex; align-items: center; gap: 0.75rem;
  font-size: 0.7rem; color: var(--text-muted);
}
.no-expiry { font-style: italic; }

.btn-sm { padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.7rem; cursor: pointer; }
.btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text-secondary); }
.btn-danger { background: transparent; border: 1px solid var(--danger); color: var(--danger); }
.btn-danger:hover { background: var(--danger-bg); }

.empty, .loading-msg { text-align: center; color: var(--text-muted); font-size: 0.85rem; padding: 1rem 0; }
</style>
