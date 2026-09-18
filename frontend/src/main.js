import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './styles.css'
import './pixel.css'
import '@fontsource/fusion-pixel-12px-proportional-sc'
import './composables/theme'

createApp(App).use(createPinia()).use(router).mount('#app')

