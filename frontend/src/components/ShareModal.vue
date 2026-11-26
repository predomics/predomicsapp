<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal" v-dialog="() => $emit('close')" aria-labelledby="share-modal-title">
      <div class="modal-header">
        <h3 id="share-modal-title">{{ $t('modals.shareProject') }}</h3>
        <button type="button" class="close-btn" :aria-label="$t('common.close')" @click="$emit('close')"><span aria-hidden="true">&times;</span></button>
      </div>

      <div class="search-section">
        <input
          v-model="query"
          type="search"
          :placeholder="$t('modals.searchByEmail')"
          :aria-label="$t('modals.searchByEmail')"
          @input="search"
          class="search-input"
          data-autofocus
        />
        <div v-if="searchResults.length > 0" class="search-results">
          <button
            v-for="u in searchResults"
            :key="u.id"
            type="button"
            class="search-item"
            @click="shareWith(u)"
          >
            <span class="user-email">{{ u.email }}</span>
            <span v-if="u.full_name" class="user-name">{{ u.full_name }}</span>
          </button>
        </div>
      </div>

      <div v-if="shares.length > 0" class="shares-list">
        <h4>{{ $t('modals.sharedWith') }}</h4>
        <div v-for="s in shares" :key="s.id" class="share-item">
          <div class="share-info">
            <span class="share-email">{{ s.email }}</span>
            <span v-if="s.full_name" class="share-name">{{ s.full_name }}</span>
          </div>
          <select :value="s.role" @change="updateRole(s, $event.target.value)" class="role-select" :aria-label="$t('modals.roleFor', { email: s.email })">
            <option value="viewer">{{ $t('modals.viewer') }}</option>
            <option value="editor">{{ $t('modals.editor') }}</option>
          </select>
          <button type="button" class="revoke-btn" @click="revoke(s)" :title="$t('modals.revokeAccess')" :aria-label="$t('modals.revokeAccess')"><span aria-hidden="true">&times;</span></button>
        </div>
      </div>

      <div v-if="message" :class="['msg', msgType]" role="status">{{ message }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import { api } from '../api'
import { apiError } from '../utils/apiError'
import { useConfirm } from '../composables/useConfirm'
import { vDialog } from '../directives/dialog'

const { confirmDialog } = useConfirm()

const { t } = useI18n()

const props = defineProps({ projectId: { type: String, required: true } })
defineEmits(['close'])

const auth = useAuthStore()
const query = ref('')
const searchResults = ref([])
const shares = ref([])
const message = ref('')
const msgType = ref('success')
let searchTimer = null

async function fetchShares() {
  try {
    const { data } = await api.projects.shares(props.projectId)
    shares.value = data
  } catch { /* ignore */ }
}

function search() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(async () => {
    if (query.value.trim().length < 3) {
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
    await api.projects.share(props.projectId, {
      email: user.email,
      role: 'viewer',
    })
    message.value = t('modals.sharedWith', { email: user.email })
    msgType.value = 'success'
    query.value = ''
    searchResults.value = []
    await fetchShares()
  } catch (e) {
    message.value = apiError(e)
    msgType.value = 'error'
  }
}

async function updateRole(share, newRole) {
  try {
    await api.projects.updateShare(props.projectId, share.id, {
      email: share.email,
      role: newRole,
    })
    share.role = newRole
  } catch (e) {
    message.value = apiError(e)
    msgType.value = 'error'
  }
}

async function revoke(share) {
  if (!(await confirmDialog({ message: t('modals.revokeAccessConfirm', { email: share.email }), danger: true }))) return
  try {
    await api.projects.revokeShare(props.projectId, share.id)
    await fetchShares()
    message.value = t('modals.revokedFor', { email: share.email })
    msgType.value = 'success'
  } catch (e) {
    message.value = apiError(e)
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
button.search-item { width: 100%; text-align: left; background: none; border: none; font: inherit; color: inherit; }
</style>
