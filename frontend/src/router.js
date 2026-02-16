import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('./views/LoginView.vue'),
    meta: { guest: true },
  },
  {
    path: '/forgot-password',
    name: 'ForgotPassword',
    component: () => import('./views/ForgotPasswordView.vue'),
    meta: { guest: true },
  },
  {
    path: '/reset-password',
    name: 'ResetPassword',
    component: () => import('./views/ResetPasswordView.vue'),
    meta: { guest: true },
  },
  {
    path: '/',
    name: 'Home',
    component: () => import('./views/HomeView.vue'),
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('./views/DashboardView.vue'),
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
      { path: '', redirect: to => ({ name: 'ProjectData', params: { id: to.params.id } }) },
      { path: 'data', name: 'ProjectData', component: () => import('./views/DataTab.vue') },
      { path: 'parameters', name: 'ProjectParameters', component: () => import('./views/ParametersTab.vue') },
      { path: 'settings', redirect: to => ({ name: 'ProjectParameters', params: { id: to.params.id } }) },
      { path: 'explore', redirect: to => ({ name: 'ProjectData', params: { id: to.params.id } }) },
      { path: 'results', name: 'ProjectResults', component: () => import('./views/ResultsTab.vue') },
      { path: 'results/:jobId', name: 'ProjectJobResults', component: () => import('./views/ResultsTab.vue') },
    ],
  },
  {
    path: '/public/:token',
    name: 'PublicShare',
    component: () => import('./views/PublicShareView.vue'),
    meta: { guest: true, public: true },
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
  // Redirect away from login if already authenticated (but allow public pages)
  if (to.meta.guest && !to.meta.public && token) {
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
