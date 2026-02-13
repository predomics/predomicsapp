import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('./views/LoginView.vue'),
    meta: { guest: true },
  },
  {
    path: '/',
    name: 'Home',
    component: () => import('./views/HomeView.vue'),
  },
  {
    path: '/projects',
    name: 'Projects',
    component: () => import('./views/ProjectsView.vue'),
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('./views/ProfileView.vue'),
  },
  {
    path: '/datasets',
    name: 'Datasets',
    component: () => import('./views/DatasetLibrary.vue'),
  },
  {
    path: '/admin',
    name: 'Admin',
    component: () => import('./views/AdminView.vue'),
    meta: { requiresAdmin: true },
  },
  {
    path: '/project/:id',
    component: () => import('./views/ProjectDashboard.vue'),
    children: [
      { path: '', redirect: to => ({ name: 'ProjectSettings', params: { id: to.params.id } }) },
      { path: 'data', redirect: to => ({ name: 'ProjectSettings', params: { id: to.params.id } }) },
      { path: 'settings', name: 'ProjectSettings', component: () => import('./views/SettingsTab.vue') },
      { path: 'results', name: 'ProjectResults', component: () => import('./views/ResultsTab.vue') },
      { path: 'results/:jobId', name: 'ProjectJobResults', component: () => import('./views/ResultsTab.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const token = localStorage.getItem('token')
  // Redirect to login if not authenticated (except guest pages)
  if (!to.meta.guest && to.name !== 'Home' && !token) {
    return { name: 'Login' }
  }
  // Redirect away from login if already authenticated
  if (to.meta.guest && token) {
    return { name: 'Projects' }
  }
  // Admin route guard
  if (to.meta.requiresAdmin && token) {
    const { useAuthStore } = await import('./stores/auth')
    const auth = useAuthStore()
    if (!auth.user) {
      await auth.fetchUser()
    }
    if (!auth.user?.is_admin) {
      return { name: 'Projects' }
    }
  }
})

export default router
