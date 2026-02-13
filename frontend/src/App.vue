<template>
  <div id="app">
    <nav class="navbar">
      <router-link to="/" class="brand">PredomicsApp</router-link>
      <div class="nav-links">
        <router-link v-if="auth.isLoggedIn" to="/projects">Projects</router-link>
      </div>
      <div class="nav-right">
        <template v-if="auth.isLoggedIn">
          <span class="user-email">{{ auth.user?.email }}</span>
          <button class="btn-logout" @click="handleLogout">Logout</button>
        </template>
        <router-link v-else to="/login" class="btn-login">Login</router-link>
      </div>
    </nav>
    <main class="container">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const router = useRouter()

onMounted(async () => {
  if (auth.token && !auth.user) {
    await auth.fetchUser()
  }
})

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #f5f7fa;
  color: #2c3e50;
}

.navbar {
  display: flex;
  align-items: center;
  padding: 0.75rem 2rem;
  background: #1a1a2e;
  color: white;
}

.navbar .brand {
  font-size: 1.25rem;
  font-weight: 700;
  color: #4fc3f7;
  text-decoration: none;
}

.nav-links {
  margin-left: 2rem;
  display: flex;
  gap: 1.5rem;
}

.nav-links a {
  color: #b0bec5;
  text-decoration: none;
  font-size: 0.9rem;
}

.nav-links a.router-link-active {
  color: white;
}

.nav-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 1rem;
}

.user-email {
  color: #b0bec5;
  font-size: 0.85rem;
}

.btn-logout {
  background: transparent;
  border: 1px solid #546e7a;
  color: #b0bec5;
  padding: 0.3rem 0.75rem;
  border-radius: 4px;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-logout:hover {
  border-color: #e53935;
  color: #e53935;
}

.btn-login {
  color: #4fc3f7;
  text-decoration: none;
  font-size: 0.9rem;
}

.container {
  max-width: 1200px;
  margin: 2rem auto;
  padding: 0 1rem;
}
</style>
