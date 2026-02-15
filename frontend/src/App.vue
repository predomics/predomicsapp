<template>
  <div id="app">
    <nav class="navbar">
      <router-link to="/" class="brand">
        <img src="/logo-dark.png" alt="PredomicsApp" class="brand-logo" />
        PredomicsApp
      </router-link>
      <div class="nav-links">
        <router-link v-if="auth.isLoggedIn" to="/projects">Projects</router-link>
        <router-link v-if="auth.isLoggedIn" to="/datasets">Datasets</router-link>
        <router-link v-if="auth.isLoggedIn && auth.isAdmin" to="/admin">Admin</router-link>
      </div>
      <div class="nav-right">
        <button class="theme-btn" @click="theme.cycle()" :title="`Theme: ${theme.mode}`">
          <span v-if="theme.mode === 'light'">&#9788;</span>
          <span v-else-if="theme.mode === 'dark'">&#9790;</span>
          <span v-else>&#9211;</span>
        </button>
        <template v-if="auth.isLoggedIn">
          <router-link to="/profile" class="user-email">{{ auth.user?.email }}</router-link>
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
import { useThemeStore } from './stores/theme'

const auth = useAuthStore()
const theme = useThemeStore()
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
/* ================================================================
   CSS Variables — Light Theme (default)
   ================================================================ */
:root {
  --bg-page: #f5f7fa;
  --bg-card: #ffffff;
  --bg-card-hover: #f5f7fa;
  --bg-input: #ffffff;
  --bg-navbar: #1a1a2e;
  --bg-badge: #f5f7fa;
  --bg-tab-switcher: #f5f5f5;

  --text-primary: #1a1a2e;
  --text-body: #2c3e50;
  --text-secondary: #546e7a;
  --text-muted: #78909c;
  --text-faint: #90a4ae;
  --text-nav-link: #b0bec5;

  --border: #cfd8dc;
  --border-light: #e0e0e0;
  --border-lighter: #eceff1;

  --shadow: 0 1px 3px rgba(0,0,0,0.1);
  --shadow-hover: 0 2px 8px rgba(0,0,0,0.15);
  --shadow-card: 0 4px 24px rgba(0,0,0,0.08);

  --accent: #1a1a2e;
  --accent-hover: #16213e;
  --accent-text: #ffffff;
  --brand: #4fc3f7;

  --success: #4caf50;
  --success-dark: #2e7d32;
  --success-bg: #e8f5e9;
  --success-bg-alt: #f1f8e9;
  --warning: #ff9800;
  --warning-dark: #e65100;
  --warning-bg: #fff3e0;
  --warning-bg-alt: #fff8e1;
  --danger: #e53935;
  --danger-dark: #c62828;
  --danger-bg: #fce4ec;
  --info: #1565c0;
  --info-bg: #e3f2fd;

  --console-bg: #1a1a2e;
  --console-text: #e0e0e0;
  --console-border: #2d2d4a;

  /* Card enhancements */
  --card-radius: 12px;
  --card-shadow: 0 1px 3px rgba(0,0,0,0.06);
  --card-shadow-hover: 0 4px 12px rgba(0,0,0,0.1);
  --card-shadow-active: 0 0 0 2px var(--brand);

  /* Stat badges (colored pills) */
  --badge-dataset: #e3f2fd;
  --badge-dataset-text: #1565c0;
  --badge-job: #f3e5f5;
  --badge-job-text: #7b1fa2;
  --badge-share: #e8f5e9;
  --badge-share-text: #2e7d32;

  /* Status indicators */
  --status-completed: #4caf50;
  --status-running: #ff9800;
  --status-failed: #e53935;

  /* Category colors (parameter sections) */
  --cat-general:        hsla(220, 60%, 55%, 0.08);
  --cat-general-bar:    hsla(220, 60%, 55%, 0.70);
  --cat-ga:             hsla(145, 55%, 42%, 0.08);
  --cat-ga-bar:         hsla(145, 55%, 42%, 0.70);
  --cat-beam:           hsla(30, 80%, 50%, 0.08);
  --cat-beam-bar:       hsla(30, 80%, 50%, 0.70);
  --cat-mcmc:           hsla(280, 50%, 55%, 0.08);
  --cat-mcmc-bar:       hsla(280, 50%, 55%, 0.70);
  --cat-cv:             hsla(195, 60%, 48%, 0.08);
  --cat-cv-bar:         hsla(195, 60%, 48%, 0.70);
  --cat-importance:     hsla(350, 60%, 55%, 0.08);
  --cat-importance-bar: hsla(350, 60%, 55%, 0.70);
  --cat-voting:         hsla(50, 70%, 45%, 0.08);
  --cat-voting-bar:     hsla(50, 70%, 45%, 0.70);
  --cat-gpu:            hsla(170, 55%, 42%, 0.08);
  --cat-gpu-bar:        hsla(170, 55%, 42%, 0.70);
}

/* ================================================================
   CSS Variables — Dark Theme
   ================================================================ */
:root.dark {
  --bg-page: #121218;
  --bg-card: #1e1e2e;
  --bg-card-hover: #282840;
  --bg-input: #282840;
  --bg-navbar: #0d0d16;
  --bg-badge: #282840;
  --bg-tab-switcher: #282840;

  --text-primary: #e8e8f0;
  --text-body: #d0d0dc;
  --text-secondary: #a0a8b8;
  --text-muted: #808898;
  --text-faint: #606878;
  --text-nav-link: #808898;

  --border: #3a3a52;
  --border-light: #2e2e44;
  --border-lighter: #252538;

  --shadow: 0 1px 3px rgba(0,0,0,0.4);
  --shadow-hover: 0 2px 8px rgba(0,0,0,0.5);
  --shadow-card: 0 4px 24px rgba(0,0,0,0.3);

  --accent: #4fc3f7;
  --accent-hover: #81d4fa;
  --accent-text: #0d0d16;
  --brand: #4fc3f7;

  --success: #66bb6a;
  --success-dark: #81c784;
  --success-bg: #1a2e1d;
  --success-bg-alt: #1a2e1d;
  --warning: #ffa726;
  --warning-dark: #ffb74d;
  --warning-bg: #2e2510;
  --warning-bg-alt: #2e2510;
  --danger: #ef5350;
  --danger-dark: #e57373;
  --danger-bg: #2e1616;
  --info: #42a5f5;
  --info-bg: #152838;

  --console-bg: #0d0d16;
  --console-text: #d0d0dc;
  --console-border: #1e1e2e;

  /* Card enhancements (dark) */
  --card-radius: 12px;
  --card-shadow: 0 1px 3px rgba(0,0,0,0.3);
  --card-shadow-hover: 0 4px 12px rgba(0,0,0,0.4);
  --card-shadow-active: 0 0 0 2px var(--brand);

  /* Stat badges (dark variants) */
  --badge-dataset: #152838;
  --badge-dataset-text: #64b5f6;
  --badge-job: #251530;
  --badge-job-text: #ce93d8;
  --badge-share: #1a2e1d;
  --badge-share-text: #81c784;

  /* Status indicators (dark) */
  --status-completed: #66bb6a;
  --status-running: #ffa726;
  --status-failed: #ef5350;

  /* Category colors (parameter sections — dark) */
  --cat-general:        hsla(220, 60%, 55%, 0.12);
  --cat-general-bar:    hsla(220, 60%, 65%, 0.80);
  --cat-ga:             hsla(145, 55%, 50%, 0.12);
  --cat-ga-bar:         hsla(145, 55%, 60%, 0.80);
  --cat-beam:           hsla(30, 80%, 55%, 0.12);
  --cat-beam-bar:       hsla(30, 80%, 65%, 0.80);
  --cat-mcmc:           hsla(280, 50%, 60%, 0.12);
  --cat-mcmc-bar:       hsla(280, 50%, 70%, 0.80);
  --cat-cv:             hsla(195, 60%, 55%, 0.12);
  --cat-cv-bar:         hsla(195, 60%, 65%, 0.80);
  --cat-importance:     hsla(350, 60%, 60%, 0.12);
  --cat-importance-bar: hsla(350, 60%, 70%, 0.80);
  --cat-voting:         hsla(50, 70%, 50%, 0.12);
  --cat-voting-bar:     hsla(50, 70%, 60%, 0.80);
  --cat-gpu:            hsla(170, 55%, 50%, 0.12);
  --cat-gpu-bar:        hsla(170, 55%, 60%, 0.80);
}

/* ================================================================
   Global Reset + Defaults
   ================================================================ */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg-page);
  color: var(--text-body);
  transition: background 0.2s, color 0.2s;
}

/* ================================================================
   Navbar
   ================================================================ */
.navbar {
  display: flex;
  align-items: center;
  padding: 0.75rem 2rem;
  background: var(--bg-navbar);
  color: white;
}

.navbar .brand {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--brand);
  text-decoration: none;
}

.brand-logo {
  height: 32px;
  width: 32px;
  object-fit: contain;
  border-radius: 4px;
}

.nav-links {
  margin-left: 2rem;
  display: flex;
  gap: 1.5rem;
}

.nav-links a {
  color: var(--text-nav-link);
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

.theme-btn {
  background: transparent;
  border: 1px solid rgba(255,255,255,0.15);
  color: var(--text-nav-link);
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  font-size: 1rem;
  cursor: pointer;
  line-height: 1;
  transition: all 0.2s;
}

.theme-btn:hover {
  border-color: var(--brand);
  color: var(--brand);
}

.user-email {
  color: var(--text-nav-link);
  font-size: 0.85rem;
  text-decoration: none;
}

.user-email:hover {
  color: var(--brand);
}

.btn-logout {
  background: transparent;
  border: 1px solid #546e7a;
  color: var(--text-nav-link);
  padding: 0.3rem 0.75rem;
  border-radius: 4px;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-logout:hover {
  border-color: var(--danger);
  color: var(--danger);
}

.btn-login {
  color: var(--brand);
  text-decoration: none;
  font-size: 0.9rem;
}

.container {
  max-width: 1600px;
  margin: 1.5rem auto;
  padding: 0 1rem;
}
</style>
