<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <div class="modal-header">
        <h3>{{ $t('modals.shareProject') }}</h3>
        <button class="close-btn" @click="$emit('close')">&times;</button>
      </div>

      <div class="search-section">
        <input
          v-model="query"
          :placeholder="$t('modals.searchByEmail')"
          @input="search"
          class="search-input"
        />
        <div v-if="searchResults.length > 0" class="search-results">
          <div
            v-for="u in searchResults"
            :key="u.id"
            class="search-item"
            @click="shareWith(u)"
          >
            <span class="user-email">{{ u.email }}</span>
            <span v-if="u.full_name" class="user-name">{{ u.full_name }}</span>
          </div>
        </div>
      </div>

      <div v-if="shares.length > 0" class="shares-list">
        <h4>{{ $t('modals.sharedWith') }}</h4>
        <div v-for="s in shares" :key="s.id" class="share-item">
          <div class="share-info">
            <span class="share-email">{{ s.email }}</span>
            <span v-if="s.full_name" class="share-name">{{ s.full_name }}</span>
          </div>
          <select :value="s.role" @change="updateRole(s, $event.target.value)" class="role-select">
            <option value="viewer">{{ $t('modals.viewer') }}</option>
            <option value="editor">{{ $t('modals.editor') }}</option>
          </select>
          <button class="revoke-btn" @click="revoke(s)" :title="$t('modals.revokeAccess')">&times;</button>
        </div>
      </div>

      <div v-if="message" :class="['msg', msgType]">{{ message }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import axios from 'axios'

const { t } = useI18n()

const props = defineProps({ projectId: String })
const emit = defineEmits(['close'])

const auth = useAuthStore()
const query = ref('')
const searchResults = ref([])
const shares = ref([])
const message = ref('')
const msgType = ref('success')
let searchTimer = null

async function fetchShares() {
  try {
    const { data } = await axios.get(`/api/projects/${props.projectId}/shares`)
    shares.value = data
  } catch { /* ignore */ }
}

function search() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(async () => {
    if (query.value.length < 2) {
      searchResults.value = []
      return
    }
    searchResults.value = await auth.searchUsers(query.value)
    // Filter out already shared users
    const sharedIds = new Set(shares.value.map(s => s.user_id))
    searchResults.value = searchResults.value.filter(u => !sharedIds.has(u.id))
  }, 300)
}

async function shareWith(user) {
  message.value = ''
  try {
    await axios.post(`/api/projects/${props.projectId}/share`, {
      email: user.email,
      role: 'viewer',
    })
    message.value = `Shared with ${user.email}`
    msgType.value = 'success'
    query.value = ''
    searchResults.value = []
    await fetchShares()
  } catch (e) {
    message.value = e.response?.data?.detail || 'Failed to share'
    msgType.value = 'error'
  }
}

async function updateRole(share, newRole) {
  try {
    await axios.put(`/api/projects/${props.projectId}/shares/${share.id}`, {
      email: share.email,
      role: newRole,
    })
    share.role = newRole
  } catch (e) {
    message.value = e.response?.data?.detail || 'Failed to update role'
    msgType.value = 'error'
  }
}

async function revoke(share) {
  if (!confirm(`Revoke access for ${share.email}?`)) return
  try {
    await axios.delete(`/api/projects/${props.projectId}/shares/${share.id}`)
    await fetchShares()
    message.value = `Revoked access for ${share.email}`
    msgType.value = 'success'
  } catch (e) {
    message.value = e.response?.data?.detail || 'Failed to revoke'
    msgType.value = 'error'
  }
}

onMounted(fetchShares)
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 1.5rem;
  width: 480px;
  max-width: 90vw;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 8px 32px rgba(0,0,0,0.2);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.modal-header h3 {
  margin: 0;
  color: var(--text-primary);
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.5rem;
  color: var(--text-faint);
  cursor: pointer;
  line-height: 1;
}

.close-btn:hover { color: var(--text-primary); }

.search-input {
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.9rem;
  background: var(--bg-input);
  color: var(--text-body);
}

.search-results {
  border: 1px solid var(--border-light);
  border-radius: 6px;
  margin-top: 0.25rem;
  max-height: 150px;
  overflow-y: auto;
}

.search-item {
  padding: 0.5rem 0.75rem;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  font-size: 0.85rem;
}

.search-item:hover { background: var(--bg-card-hover); }

.user-email { color: var(--text-body); }
.user-name { color: var(--text-muted); font-size: 0.8rem; }

.shares-list {
  margin-top: 1.25rem;
}

.shares-list h4 {
  color: var(--text-secondary);
  font-size: 0.85rem;
  margin-bottom: 0.5rem;
}

.share-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border-lighter);
}

.share-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.share-email { font-size: 0.85rem; color: var(--text-body); }
.share-name { font-size: 0.75rem; color: var(--text-muted); }

.role-select {
  padding: 0.2rem 0.4rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 0.8rem;
  background: var(--bg-input);
  color: var(--text-body);
}

.revoke-btn {
  background: none;
  border: none;
  font-size: 1.2rem;
  color: var(--text-faint);
  cursor: pointer;
  padding: 0 0.3rem;
  line-height: 1;
}

.revoke-btn:hover { color: var(--danger); }

.msg {
  margin-top: 0.75rem;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  font-size: 0.82rem;
}

.msg.success { background: var(--success-bg); color: var(--success-dark); }
.msg.error { background: var(--danger-bg); color: var(--danger-dark); }
</style>
