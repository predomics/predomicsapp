<template>
  <div class="admin-page">
    <h2>User Administration</h2>

    <div v-if="loading" class="loading">Loading users...</div>
    <div v-else-if="error" class="error-msg">{{ error }}</div>

    <table v-else class="user-table">
      <thead>
        <tr>
          <th>Email</th>
          <th>Name</th>
          <th>Active</th>
          <th>Admin</th>
          <th>Projects</th>
          <th>Datasets</th>
          <th>Created</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="u in users" :key="u.id" :class="{ inactive: !u.is_active }">
          <td>{{ u.email }}</td>
          <td>{{ u.full_name || '—' }}</td>
          <td>
            <button
              class="toggle-btn"
              :class="u.is_active ? 'on' : 'off'"
              @click="toggleActive(u)"
              :disabled="u.id === currentUser.id"
            >
              {{ u.is_active ? 'Yes' : 'No' }}
            </button>
          </td>
          <td>
            <button
              class="toggle-btn"
              :class="u.is_admin ? 'on' : 'off'"
              @click="toggleAdmin(u)"
              :disabled="u.id === currentUser.id"
            >
              {{ u.is_admin ? 'Yes' : 'No' }}
            </button>
          </td>
          <td class="count">{{ u.project_count }}</td>
          <td class="count">{{ u.dataset_count }}</td>
          <td class="date">{{ new Date(u.created_at).toLocaleDateString() }}</td>
          <td>
            <button
              class="btn-delete"
              @click="deleteUser(u)"
              :disabled="u.id === currentUser.id"
            >
              Delete
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const currentUser = auth.user

const users = ref([])
const loading = ref(true)
const error = ref('')

async function fetchUsers() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await axios.get('/api/admin/users')
    users.value = data
  } catch (e) {
    error.value = e.response?.data?.detail || 'Failed to load users'
  } finally {
    loading.value = false
  }
}

async function toggleActive(u) {
  try {
    const { data } = await axios.patch(`/api/admin/users/${u.id}`, {
      is_active: !u.is_active,
    })
    Object.assign(u, data)
  } catch (e) {
    alert(e.response?.data?.detail || 'Failed to update user')
  }
}

async function toggleAdmin(u) {
  try {
    const { data } = await axios.patch(`/api/admin/users/${u.id}`, {
      is_admin: !u.is_admin,
    })
    Object.assign(u, data)
  } catch (e) {
    alert(e.response?.data?.detail || 'Failed to update user')
  }
}

async function deleteUser(u) {
  if (!confirm(`Delete user "${u.email}" and ALL their data? This cannot be undone.`)) return
  try {
    await axios.delete(`/api/admin/users/${u.id}`)
    users.value = users.value.filter(x => x.id !== u.id)
  } catch (e) {
    alert(e.response?.data?.detail || 'Failed to delete user')
  }
}

onMounted(fetchUsers)
</script>

<style scoped>
.admin-page {
  max-width: 1100px;
  margin: 0 auto;
}

.admin-page h2 {
  margin-bottom: 1.5rem;
  color: var(--text-primary);
}

.loading, .error-msg {
  text-align: center;
  padding: 2rem;
  color: var(--text-muted);
}

.error-msg { color: var(--danger); }

.user-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--bg-card);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: var(--shadow);
}

.user-table th, .user-table td {
  padding: 0.6rem 0.75rem;
  text-align: left;
  font-size: 0.85rem;
  border-bottom: 1px solid var(--border-lighter);
}

.user-table th {
  background: var(--bg-badge);
  color: var(--text-secondary);
  font-weight: 600;
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.user-table tr.inactive td {
  opacity: 0.5;
}

.count { text-align: center; }
.date { white-space: nowrap; color: var(--text-muted); }

.toggle-btn {
  padding: 0.2rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.78rem;
  font-weight: 500;
  background: var(--bg-input);
  color: var(--text-body);
  transition: all 0.15s;
}

.toggle-btn.on {
  background: var(--success-bg);
  color: var(--success-dark);
  border-color: var(--success);
}

.toggle-btn.off {
  background: var(--bg-input);
  color: var(--text-muted);
}

.toggle-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.btn-delete {
  padding: 0.2rem 0.5rem;
  background: transparent;
  border: 1px solid var(--danger);
  color: var(--danger);
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.78rem;
  transition: all 0.15s;
}

.btn-delete:hover {
  background: var(--danger-bg);
}

.btn-delete:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
</style>
