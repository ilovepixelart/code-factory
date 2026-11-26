import { VueQueryPlugin } from '@tanstack/vue-query'
import { createApp, h } from 'vue'
import { RouterView } from 'vue-router'
import App from './App.vue'
import { watchFailures } from './lib/failures'
import { createQueryClient } from './lib/queries'
import { router } from './router'
import './styles/app.css'

// A reply link's page has no sign-in: without the shell, which reads and polls the whole board.
const shell = window.location.pathname.startsWith('/reply/') ? () => h(RouterView) : App
const app = createApp(shell).use(router).use(VueQueryPlugin, { queryClient: createQueryClient() })
watchFailures(app)
app.mount('#app')
