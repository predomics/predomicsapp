<template>
  <div class="comments-sidebar" :class="{ open: visible }">
    <div class="sidebar-header">
      <h3>Notes</h3>
      <button class="close-btn" @click="$emit('close')">&times;</button>
    </div>

    <div class="comments-list" ref="listEl">
      <div v-if="loading" class="loading-msg">Loading...</div>
      <div v-else-if="comments.length === 0" class="empty-msg">No notes yet. Be the first to add one.</div>
      <div v-for="c in comments" :key="c.id" class="comment">
        <div class="comment-header">
          <span class="comment-user">{{ c.user_name }}</span>
          <span class="comment-time">{{ timeAgo(c.created_at) }}</span>
          <span v-if="c.updated_at" class="comment-edited">(edited)</span>
        </div>
        <div v-if="editingId === c.id" class="edit-form">
          <textarea v-model="editContent" rows="2" class="comment-textarea"></textarea>
          <div class="edit-actions">
            <button class="btn-sm btn-primary" @click="saveEdit(c.id)">Save</button>
            <button class="btn-sm btn-outline" @click="editingId = null">Cancel</button>
          </div>
        </div>
        <div v-else class="comment-content">{{ c.content }}</div>
        <div v-if="c.user_id === currentUserId && editingId !== c.id" class="comment-actions">
          <button class="action-btn" @click="startEdit(c)">Edit</button>
          <button class="action-btn action-delete" @click="deleteComment(c.id)">Delete</button>
        </div>
      </div>
    </div>

    <div class="add-comment">
      <textarea
        v-model="newContent"
        placeholder="Add a note..."
        rows="2"
        class="comment-textarea"
        @keydown.ctrl.enter="addComment"
      ></textarea>
      <button class="btn-sm btn-primary" :disabled="!newContent.trim()" @click="addComment">
        Add
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import axios from 'axios'
import { useAuthStore } from '../stores/auth'

const props = defineProps({
  projectId: String,
  visible: Boolean,
})
const emit = defineEmits(['close'])

const auth = useAuthStore()
const currentUserId = auth.user?.id

const comments = ref([])
const loading = ref(true)
const newContent = ref('')
const editingId = ref(null)
const editContent = ref('')
const listEl = ref(null)

async function loadComments() {
  loading.value = true
  try {
    const { data } = await axios.get(`/api/projects/${props.projectId}/comments`)
    comments.value = data
  } catch (e) {
    console.error('Failed to load comments:', e)
  } finally {
    loading.value = false
  }
}

async function addComment() {
  if (!newContent.value.trim()) return
  try {
    const { data } = await axios.post(`/api/projects/${props.projectId}/comments`, {
      content: newContent.value.trim(),
    })
    comments.value.push(data)
    newContent.value = ''
    await nextTick()
    if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
  } catch (e) {
    alert('Failed to add comment: ' + (e.response?.data?.detail || e.message))
  }
}

function startEdit(comment) {
  editingId.value = comment.id
  editContent.value = comment.content
}

async function saveEdit(id) {
  try {
    const { data } = await axios.put(`/api/projects/${props.projectId}/comments/${id}`, {
      content: editContent.value.trim(),
    })
    const idx = comments.value.findIndex(c => c.id === id)
    if (idx !== -1) {
      comments.value[idx].content = data.content
      comments.value[idx].updated_at = data.updated_at
    }
    editingId.value = null
  } catch (e) {
    alert('Failed to update: ' + (e.response?.data?.detail || e.message))
  }
}

async function deleteComment(id) {
  if (!confirm('Delete this note?')) return
  try {
    await axios.delete(`/api/projects/${props.projectId}/comments/${id}`)
    comments.value = comments.value.filter(c => c.id !== id)
  } catch (e) {
    alert('Failed to delete: ' + (e.response?.data?.detail || e.message))
  }
}

function timeAgo(isoStr) {
  if (!isoStr) return ''
  const diff = Date.now() - new Date(isoStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

onMounted(() => {
  if (props.projectId) loadComments()
})
</script>

<style scoped>
.comments-sidebar {
  position: fixed; top: 0; right: -380px;
  width: 360px; height: 100vh;
  background: var(--bg-card);
  border-left: 1px solid var(--border);
  box-shadow: -4px 0 20px rgba(0,0,0,0.2);
  z-index: 999;
  display: flex; flex-direction: column;
  transition: right 0.25s ease;
}
.comments-sidebar.open { right: 0; }

.sidebar-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border);
}
.sidebar-header h3 { margin: 0; font-size: 1.1rem; }
.close-btn {
  background: none; border: none; color: var(--text-muted);
  font-size: 1.4rem; cursor: pointer; line-height: 1;
}
.close-btn:hover { color: var(--text-primary); }

.comments-list {
  flex: 1; overflow-y: auto; padding: 0.75rem 1.25rem;
}

.loading-msg, .empty-msg {
  text-align: center; color: var(--text-muted);
  font-size: 0.85rem; padding: 2rem 0;
}

.comment {
  margin-bottom: 1rem; padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--border-light);
}
.comment:last-child { border-bottom: none; }

.comment-header {
  display: flex; align-items: center; gap: 0.4rem;
  margin-bottom: 0.3rem;
}
.comment-user { font-weight: 600; font-size: 0.8rem; color: var(--text-primary); }
.comment-time { font-size: 0.7rem; color: var(--text-muted); margin-left: auto; }
.comment-edited { font-size: 0.65rem; color: var(--text-faint); font-style: italic; }

.comment-content {
  font-size: 0.85rem; color: var(--text-body);
  white-space: pre-wrap; word-break: break-word;
}

.comment-actions {
  display: flex; gap: 0.5rem; margin-top: 0.3rem;
}
.action-btn {
  background: none; border: none; font-size: 0.7rem;
  color: var(--text-muted); cursor: pointer; padding: 0;
}
.action-btn:hover { color: var(--accent); }
.action-delete:hover { color: var(--danger); }

.edit-form { margin-top: 0.3rem; }
.edit-actions { display: flex; gap: 0.4rem; margin-top: 0.3rem; }

.add-comment {
  padding: 0.75rem 1.25rem;
  border-top: 1px solid var(--border);
  display: flex; gap: 0.5rem; align-items: flex-end;
}

.comment-textarea {
  flex: 1; resize: vertical;
  background: var(--bg-input); color: var(--text-body);
  border: 1px solid var(--border); border-radius: 6px;
  padding: 0.5rem; font-size: 0.8rem; font-family: inherit;
}
.comment-textarea:focus { outline: none; border-color: var(--accent); }

.btn-sm { padding: 0.3rem 0.7rem; border-radius: 4px; font-size: 0.75rem; cursor: pointer; }
.btn-primary { background: var(--accent); color: var(--accent-text); border: none; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text-secondary); }
</style>
