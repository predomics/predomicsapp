import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const user = ref(null)

  const isLoggedIn = computed(() => !!token.value)

  // Set axios default header whenever token changes
  function setToken(t) {
    token.value = t
    if (t) {
      localStorage.setItem('token', t)
      axios.defaults.headers.common['Authorization'] = `Bearer ${t}`
    } else {
      localStorage.removeItem('token')
      delete axios.defaults.headers.common['Authorization']
    }
  }

  // Restore token on app load
  if (token.value) {
    axios.defaults.headers.common['Authorization'] = `Bearer ${token.value}`
  }

  async function login(email, password) {
    const { data } = await axios.post('/api/auth/login', { email, password })
    setToken(data.access_token)
    await fetchUser()
  }

  async function register(email, password, full_name) {
    await axios.post('/api/auth/register', { email, password, full_name })
    await login(email, password)
  }

  async function fetchUser() {
    try {
      const { data } = await axios.get('/api/auth/me')
      user.value = data
    } catch {
      logout()
    }
  }

  function logout() {
    setToken('')
    user.value = null
  }

  return { token, user, isLoggedIn, login, register, fetchUser, logout }
})
