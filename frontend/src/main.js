import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'
import './styles.css'
import './pixel.css'
// 夜间覆盖必须排在 pixel.css 之后：像素风的硬编码奶油色要由它接管
import './night.css'
import '@fontsource/fusion-pixel-12px-proportional-sc'
import { initTheme } from './composables/theme'

const app = createApp(App).use(createPinia())
// 主题模块在 import 时就落地 data-theme/data-mode（避免首屏闪烁）；
// 账号里的外观偏好要等 Pinia 就绪后才能读，所以这里把 auth store 注入进去补一次同步。
initTheme(useAuthStore())
app.use(router).mount('#app')
