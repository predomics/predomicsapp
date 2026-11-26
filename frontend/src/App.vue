<template>
  <div id="app">
    <a href="#main-content" class="skip-link">{{ $t('nav.skipToContent') }}</a>
    <nav class="navbar" :aria-label="$t('nav.mainNavigation')">
      <router-link to="/" class="brand">
        <img src="/logo-dark.png" alt="PredomicsApp" class="brand-logo" />
        PredomicsApp
      </router-link>
      <button
        type="button"
        class="nav-toggle"
        :aria-expanded="navOpen ? 'true' : 'false'"
        aria-controls="nav-links"
        :aria-label="$t('nav.toggleMenu')"
        @click="navOpen = !navOpen"
      >&#9776;</button>
      <div id="nav-links" :class="['nav-links', { open: navOpen }]">
        <router-link v-if="auth.isLoggedIn && !uiMode.isSimple" to="/dashboard">{{ $t('nav.dashboard') }}</router-link>
        <router-link v-if="auth.isLoggedIn" to="/projects">{{ $t('nav.projects') }}</router-link>
        <template v-if="auth.isLoggedIn && !uiMode.isSimple">
          <router-link to="/datasets">{{ $t('nav.datasets') }}</router-link>
          <router-link to="/meta-analysis">{{ $t('nav.metaAnalysis') }}</router-link>
          <router-link to="/signature-zoo">{{ $t('nav.signatureZoo') }}</router-link>
        </template>
        <router-link v-if="auth.isLoggedIn && auth.isAdmin" to="/admin">{{ $t('nav.admin') }}</router-link>
        <router-link to="/credits">{{ $t('nav.credits') }}</router-link>
      </div>
      <div class="nav-right">
        <button
          v-if="auth.isLoggedIn"
          type="button"
          role="switch"
          class="mode-switch"
          :aria-checked="uiMode.isSimple ? 'true' : 'false'"
          :title="$t('nav.modeHint')"
          @click="uiMode.toggle()"
        >
          <span :class="['mode-opt', { on: uiMode.isSimple }]">{{ $t('nav.modeSimple') }}</span>
          <span :class="['mode-opt', { on: !uiMode.isSimple }]">{{ $t('nav.modeExpert') }}</span>
        </button>
        <button type="button" class="lang-btn" @click="toggleLocale" :title="currentLocaleInfo.name" :aria-label="$t('nav.switchLanguage', { name: currentLocaleInfo.name })">
          <span class="lang-flag" aria-hidden="true">{{ currentLocaleInfo.flag }}</span>
          <span class="lang-code">{{ currentLocaleInfo.label }}</span>
        </button>
        <button type="button" class="theme-btn" @click="theme.cycle()" :title="themeLabel" :aria-label="themeLabel">
          <span v-if="theme.mode === 'light'" aria-hidden="true">&#9788;</span>
          <span v-else-if="theme.mode === 'dark'" aria-hidden="true">&#9790;</span>
          <span v-else aria-hidden="true">&#9211;</span>
        </button>
        <template v-if="auth.isLoggedIn">
          <router-link to="/profile" class="user-email">{{ auth.user?.email }}</router-link>
          <button type="button" class="btn-logout" @click="handleLogout">{{ $t('nav.logout') }}</button>
        </template>
        <router-link v-else to="/login" class="btn-login">{{ $t('nav.login') }}</router-link>
      </div>
    </nav>
    <main id="main-content" class="container" tabindex="-1">
      <router-view />
    </main>
    <ConfirmDialog />
    <ToastContainer />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from './stores/auth'
import { useThemeStore } from './stores/theme'
import { useUiModeStore } from './stores/uiMode'
import { LOCALES, applyDocumentLang } from './i18n'
import ToastContainer from './components/ToastContainer.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'

const auth = useAuthStore()
const theme = useThemeStore()
const uiMode = useUiModeStore()
const router = useRouter()
const route = useRoute()
const { locale, t } = useI18n()

const navOpen = ref(false)
watch(() => route.fullPath, () => { navOpen.value = false })

const themeLabel = computed(() => t('nav.theme', { mode: t(`nav.themeMode.${theme.mode}`) }))
watch(locale, (code) => applyDocumentLang(code), { immediate: true })
const currentLocaleInfo = computed(() => LOCALES.find(l => l.code === locale.value) || LOCALES[0])

function toggleLocale() {
  const codes = LOCALES.map(l => l.code)
  const idx = codes.indexOf(locale.value)
  locale.value = codes[(idx + 1) % codes.length]
  localStorage.setItem('locale', locale.value)
}

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
  --text-muted: #546e7a;
  --text-faint: #5d717d;
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
  --tab-active: #1d4ed8;
  --brand: #4fc3f7;

  --success: #4caf50;
  --success-dark: #2e7d32;
  --success-bg: #e8f5e9;
  --success-bg-alt: #f1f8e9;
  --warning: #ff9800;
  --warning-dark: #c24400;
  --warning-bg: #fff3e0;
  --warning-bg-alt: #fff8e1;
  --danger: #cd1e1a;
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
  --cat-feature-selection: hsla(205, 55%, 45%, 0.08);
  --cat-feature-selection-bar: hsla(205, 55%, 45%, 0.70);
  --cat-sa: hsla(15, 70%, 50%, 0.08);
  --cat-sa-bar: hsla(15, 70%, 50%, 0.70);
  --cat-lasso: hsla(260, 45%, 55%, 0.08);
  --cat-lasso-bar: hsla(260, 45%, 55%, 0.70);
  --cat-ils: hsla(95, 45%, 40%, 0.08);
  --cat-ils-bar: hsla(95, 45%, 40%, 0.70);
  --cat-aco: hsla(40, 75%, 45%, 0.08);
  --cat-aco-bar: hsla(40, 75%, 45%, 0.70);
  --cat-rf: hsla(125, 45%, 38%, 0.08);
  --cat-rf-bar: hsla(125, 45%, 38%, 0.70);
  --cat-svm: hsla(300, 40%, 50%, 0.08);
  --cat-svm-bar: hsla(300, 40%, 50%, 0.70);
  --cat-logistic: hsla(185, 55%, 40%, 0.08);
  --cat-logistic-bar: hsla(185, 55%, 40%, 0.70);
  --cat-xgboost: hsla(5, 65%, 52%, 0.08);
  --cat-xgboost-bar: hsla(5, 65%, 52%, 0.70);
  --cat-lightgbm: hsla(75, 55%, 38%, 0.08);
  --cat-lightgbm-bar: hsla(75, 55%, 38%, 0.70);
  --cat-extra_trees: hsla(155, 50%, 38%, 0.08);
  --cat-extra_trees-bar: hsla(155, 50%, 38%, 0.70);
  --cat-adaboost: hsla(330, 55%, 52%, 0.08);
  --cat-adaboost-bar: hsla(330, 55%, 52%, 0.70);
  --cat-knn: hsla(240, 50%, 58%, 0.08);
  --cat-knn-bar: hsla(240, 50%, 58%, 0.70);
  --cat-clinical: hsla(20, 60%, 48%, 0.08);
  --cat-clinical-bar: hsla(20, 60%, 48%, 0.70);
}

/* ================================================================
   Aliases used by components. They point at the theme tokens above, so
   they follow light and dark (used to be undefined: components fell back
   to light colours in dark mode). Defined once; never redefine per theme.
   ================================================================ */
:root {
  --bg-primary: var(--bg-page);
  --bg-surface: var(--bg-card);
  --bg-surface-alt: var(--bg-badge);
  --bg-secondary: var(--bg-badge);
  --bg-hover: var(--bg-card-hover);
  --bg-active: var(--info-bg);
  --bg-highlight: var(--warning-bg-alt);
  --accent-bg: var(--info-bg);
  --accent-faint: var(--info-bg);
  --brand-bg: var(--info-bg);
  --border-color: var(--border);
  --text: var(--text-body);
  --primary: var(--tab-active);
  --positive: var(--success);
  --negative: var(--danger);
  --warn: var(--warning);
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
  --text-muted: #a0a8b8;
  --text-faint: #9098a8;
  --text-nav-link: #a8b0c0;

  --border: #3a3a52;
  --border-light: #2e2e44;
  --border-lighter: #252538;

  --shadow: 0 1px 3px rgba(0,0,0,0.4);
  --shadow-hover: 0 2px 8px rgba(0,0,0,0.5);
  --shadow-card: 0 4px 24px rgba(0,0,0,0.3);

  --accent: #4fc3f7;
  --accent-hover: #81d4fa;
  --accent-text: #0d0d16;
  --tab-active: #4fc3f7;
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
  --cat-feature-selection: hsla(205, 55%, 53%, 0.12);
  --cat-feature-selection-bar: hsla(205, 55%, 63%, 0.80);
  --cat-sa: hsla(15, 70%, 58%, 0.12);
  --cat-sa-bar: hsla(15, 70%, 68%, 0.80);
  --cat-lasso: hsla(260, 45%, 63%, 0.12);
  --cat-lasso-bar: hsla(260, 45%, 73%, 0.80);
  --cat-ils: hsla(95, 45%, 48%, 0.12);
  --cat-ils-bar: hsla(95, 45%, 58%, 0.80);
  --cat-aco: hsla(40, 75%, 53%, 0.12);
  --cat-aco-bar: hsla(40, 75%, 63%, 0.80);
  --cat-rf: hsla(125, 45%, 46%, 0.12);
  --cat-rf-bar: hsla(125, 45%, 56%, 0.80);
  --cat-svm: hsla(300, 40%, 58%, 0.12);
  --cat-svm-bar: hsla(300, 40%, 68%, 0.80);
  --cat-logistic: hsla(185, 55%, 48%, 0.12);
  --cat-logistic-bar: hsla(185, 55%, 58%, 0.80);
  --cat-xgboost: hsla(5, 65%, 60%, 0.12);
  --cat-xgboost-bar: hsla(5, 65%, 70%, 0.80);
  --cat-lightgbm: hsla(75, 55%, 46%, 0.12);
  --cat-lightgbm-bar: hsla(75, 55%, 56%, 0.80);
  --cat-extra_trees: hsla(155, 50%, 46%, 0.12);
  --cat-extra_trees-bar: hsla(155, 50%, 56%, 0.80);
  --cat-adaboost: hsla(330, 55%, 60%, 0.12);
  --cat-adaboost-bar: hsla(330, 55%, 70%, 0.80);
  --cat-knn: hsla(240, 50%, 66%, 0.12);
  --cat-knn-bar: hsla(240, 50%, 76%, 0.80);
  --cat-clinical: hsla(20, 60%, 56%, 0.12);
  --cat-clinical-bar: hsla(20, 60%, 66%, 0.80);
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

/* Visible keyboard focus everywhere (mouse clicks are unaffected). */
:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 2px;
}
main:focus { outline: none; }

.skip-link {
  position: absolute;
  left: -9999px;
  top: 0;
  background: var(--bg-card);
  color: var(--text-primary);
  padding: 0.5rem 1rem;
  z-index: 10001;
  border-radius: 0 0 6px 0;
}
.skip-link:focus { left: 0; }

.sr-only {
  position: absolute;
  width: 1px; height: 1px;
  padding: 0; margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
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
  text-decoration: underline;
  text-underline-offset: 4px;
}

.nav-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 1rem;
}

.lang-btn {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  background: transparent;
  border: 1px solid rgba(255,255,255,0.15);
  color: var(--text-nav-link);
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 700;
  cursor: pointer;
  line-height: 1;
  transition: all 0.2s;
  letter-spacing: 0.5px;
  min-width: 52px;
  justify-content: center;
}

.lang-flag {
  font-size: 0.9rem;
  line-height: 1;
}

.lang-code {
  font-size: 0.75rem;
}

.lang-btn:hover {
  border-color: var(--brand);
  color: var(--brand);
}

.mode-switch {
  display: inline-flex;
  padding: 2px;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.15);
  border-radius: 999px;
  cursor: pointer;
  font-size: 0.75rem;
  font-weight: 600;
}
.mode-opt {
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  color: var(--text-nav-link);
  transition: background 0.15s, color 0.15s;
}
.mode-opt.on {
  background: var(--brand);
  color: #0d0d16;
}
.mode-switch:hover { border-color: var(--brand); }

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

.nav-toggle {
  display: none;
  margin-left: 1rem;
  background: transparent;
  border: 1px solid rgba(255,255,255,0.25);
  color: #fff;
  border-radius: 6px;
  font-size: 1.1rem;
  padding: 0.2rem 0.55rem;
  cursor: pointer;
}

@media (max-width: 1100px) {
  .navbar { flex-wrap: wrap; padding: 0.6rem 1rem; row-gap: 0.5rem; }
  .nav-toggle { display: inline-block; order: 2; margin-left: auto; }
  .nav-right { order: 3; margin-left: 0.75rem; gap: 0.5rem; }
  .nav-links {
    order: 4;
    display: none;
    flex-direction: column;
    gap: 0.25rem;
    width: 100%;
    margin-left: 0;
  }
  .nav-links.open { display: flex; }
  .nav-links a { padding: 0.45rem 0.25rem; }
  .user-email { max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
}
@media (max-width: 560px) {
  .user-email { display: none; }
}
</style>
