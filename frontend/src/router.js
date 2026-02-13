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
    path: '/project/:id',
    component: () => import('./views/ProjectDashboard.vue'),
    children: [
      { path: '', redirect: to => ({ name: 'ProjectData', params: { id: to.params.id } }) },
      { path: 'data', name: 'ProjectData', component: () => import('./views/DataTab.vue') },
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

router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  // Redirect to login if not authenticated (except guest pages)
  if (!to.meta.guest && to.name !== 'Home' && !token) {
    return { name: 'Login' }
  }
  // Redirect away from login if already authenticated
  if (to.meta.guest && token) {
    return { name: 'Projects' }
  }
})

export default router
