import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import i18n from './i18n'
import { useToast } from './composables/useToast'
import { useAuthStore } from './stores/auth'
import { setupHttp } from './utils/http'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(i18n)
app.use(router)

// One place for request timeout, language header, session expiry and error toasts.
const { addToast } = useToast()
setupHttp({ router, i18n, addToast, getAuthStore: () => useAuthStore(pinia) })

app.mount('#app')
