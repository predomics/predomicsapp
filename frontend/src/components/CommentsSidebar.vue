<template>
  <aside class="comments-sidebar" :class="{ open: visible }" :aria-hidden="visible ? 'false' : 'true'" :inert="!visible" aria-labelledby="comments-title" @keydown.escape="$emit('close')">
    <div class="sidebar-header">
      <h3 id="comments-title">{{ $t('comments.notes') }}</h3>
      <button type="button" class="close-btn" :aria-label="$t('common.close')" @click="$emit('close')"><span aria-hidden="true">&times;</span></button>
    </div>

    <div class="comments-list" ref="listEl">
      <div v-if="loading" class="loading-msg">{{ $t('comments.loading') }}</div>
      <div v-else-if="comments.length === 0" class="empty-msg">{{ $t('comments.noNotes') }}</div>
      <div v-for="c in comments" :key="c.id" class="comment">
        <div class="comment-header">
          <span class="comment-user">{{ c.user_name }}</span>
          <span class="comment-time">{{ timeAgo(c.created_at) }}</span>
          <span v-if="c.updated_at" class="comment-edited">{{ $t('comments.edited') }}</span>
        </div>
        <div v-if="editingId === c.id" class="edit-form">
          <textarea :aria-label="$t('comments.editLabel')" v-model="editContent" rows="2" class="comment-textarea"></textarea>
          <div class="edit-actions">
            <button class="btn-sm btn-primary" @click="saveEdit(c.id)">{{ $t('comments.save') }}</button>
            <button class="btn-sm btn-outline" @click="editingId = null">{{ $t('comments.cancel') }}</button>
          </div>
        </div>
        <div v-else class="comment-content">{{ c.content }}</div>
        <div v-if="c.user_id === currentUserId && editingId !== c.id" class="comment-actions">
          <button class="action-btn" @click="startEdit(c)">{{ $t('comments.editBtn') }}</button>
          <button class="action-btn action-delete" @click="deleteComment(c.id)">{{ $t('comments.deleteBtn') }}</button>
        </div>
      </div>
    </div>

    <div class="add-comment">
      <textarea :aria-label="$t('comments.placeholder')"
        v-model="newContent"
        :placeholder="$t('comments.placeholder')"
        rows="2"
        class="comment-textarea"
        @keydown.ctrl.enter="addComment"
      ></textarea>
      <button class="btn-sm btn-primary" :disabled="!newContent.trim()" @click="addComment">
        {{ $t('comments.add') }}
      </button>
    </div>
  </aside>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { timeAgo } from '../utils/time'
import { useAuthStore } from '../stores/auth'
import { apiError } from '../utils/apiError'
import { useToast } from '../composables/useToast'
import { useConfirm } from '../composables/useConfirm'

const { toast } = useToast()
const { confirmDialog } = useConfirm()

const { t } = useI18n()

const props = defineProps({
  projectId: { type: String, required: true },
  visible: Boolean,
})
defineEmits(['close'])

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
    const { data } = await api.projects.comments(props.projectId)
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
    const { data } = await api.projects.addComment(props.projectId, {
      content: newContent.value.trim(),
    })
    comments.value.push(data)
    newContent.value = ''
    await nextTick()
    if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
  } catch (e) {
    toast.error(t('comments.addFailed', { error: apiError(e) }))
  }
}

function startEdit(comment) {
  editingId.value = comment.id
  editContent.value = comment.content
}

async function saveEdit(id) {
  try {
    const { data } = await api.projects.updateComment(props.projectId, id, {
      content: editContent.value.trim(),
    })
    const idx = comments.value.findIndex(c => c.id === id)
    if (idx !== -1) {
      comments.value[idx].content = data.content
      comments.value[idx].updated_at = data.updated_at
    }
    editingId.value = null
  } catch (e) {
    toast.error(t('comments.updateFailed', { error: apiError(e) }))
  }
}

async function deleteComment(id) {
  if (!(await confirmDialog({ message: t('comments.deleteConfirm'), danger: true }))) return
  try {
    await api.projects.deleteComment(props.projectId, id)
    comments.value = comments.value.filter(c => c.id !== id)
  } catch (e) {
    toast.error(t('comments.deleteFailed', { error: apiError(e) }))
  }
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
.comment-time { font-size: 0.75rem; color: var(--text-muted); margin-left: auto; }
.comment-edited { font-size: 0.75rem; color: var(--text-faint); font-style: italic; }

.comment-content {
  font-size: 0.85rem; color: var(--text-body);
  white-space: pre-wrap; word-break: break-word;
}

.comment-actions {
  display: flex; gap: 0.5rem; margin-top: 0.3rem;
}
.action-btn {
  background: none; border: none; font-size: 0.75rem;
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
.comment-textarea:focus { border-color: var(--accent); }

.btn-sm { padding: 0.3rem 0.7rem; border-radius: 4px; font-size: 0.75rem; cursor: pointer; }
.btn-primary { background: var(--accent); color: var(--accent-text); border: none; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text-secondary); }
</style>
