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
    name: 'Project',
    component: () => import('./views/ProjectView.vue'),
  },
  {
    path: '/project/:id/run',
    name: 'RunAnalysis',
    component: () => import('./views/RunView.vue'),
  },
  {
    path: '/project/:id/results/:jobId',
    name: 'Results',
    component: () => import('./views/ResultsView.vue'),
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
