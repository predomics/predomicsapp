<template>
  <div class="login-page">
    <div class="login-card">
      <h1 class="login-title">PredomicsApp</h1>
      <p class="login-subtitle">Microbiome-based classification</p>

      <div class="tab-switcher">
        <button :class="{ active: mode === 'login' }" @click="mode = 'login'">Login</button>
        <button :class="{ active: mode === 'register' }" @click="mode = 'register'">Register</button>
      </div>

      <form @submit.prevent="submit">
        <div v-if="mode === 'register'" class="field">
          <label>Full Name</label>
          <input v-model="fullName" type="text" placeholder="Your name" />
        </div>
        <div class="field">
          <label>Email</label>
          <input v-model="email" type="email" placeholder="email@example.com" required />
        </div>
        <div class="field">
          <label>Password</label>
          <input v-model="password" type="password" placeholder="Password" required />
        </div>
        <p v-if="error" class="error">{{ error }}</p>
        <button type="submit" class="btn-primary" :disabled="loading">
          {{ loading ? 'Please wait...' : (mode === 'login' ? 'Login' : 'Create Account') }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

const mode = ref('login')
const email = ref('')
const password = ref('')
const fullName = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    if (mode.value === 'login') {
      await auth.login(email.value, password.value)
    } else {
      await auth.register(email.value, password.value, fullName.value)
    }
    router.push('/projects')
  } catch (e) {
    const detail = e.response?.data?.detail
    error.value = detail || 'Something went wrong. Please try again.'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 80vh;
}

.login-card {
  background: white;
  border-radius: 12px;
  padding: 2.5rem;
  width: 100%;
  max-width: 400px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08);
}

.login-title {
  text-align: center;
  color: #1a1a2e;
  font-size: 1.75rem;
  margin-bottom: 0.25rem;
}

.login-subtitle {
  text-align: center;
  color: #78909c;
  font-size: 0.9rem;
  margin-bottom: 1.5rem;
}

.tab-switcher {
  display: flex;
  gap: 0;
  margin-bottom: 1.5rem;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #e0e0e0;
}

.tab-switcher button {
  flex: 1;
  padding: 0.6rem;
  border: none;
  background: #f5f5f5;
  color: #78909c;
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.2s;
}

.tab-switcher button.active {
  background: #1a1a2e;
  color: white;
}

.field {
  margin-bottom: 1rem;
}

.field label {
  display: block;
  font-size: 0.85rem;
  font-weight: 500;
  color: #546e7a;
  margin-bottom: 0.3rem;
}

.field input {
  width: 100%;
  padding: 0.6rem 0.75rem;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  font-size: 0.9rem;
  outline: none;
  transition: border-color 0.2s;
}

.field input:focus {
  border-color: #4fc3f7;
}

.error {
  color: #e53935;
  font-size: 0.85rem;
  margin-bottom: 0.75rem;
}

.btn-primary {
  width: 100%;
  padding: 0.7rem;
  background: #1a1a2e;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 0.95rem;
  cursor: pointer;
  transition: background 0.2s;
  margin-top: 0.5rem;
}

.btn-primary:hover {
  background: #2d2d4e;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
