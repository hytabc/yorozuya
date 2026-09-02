import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 本地开发默认直连本机后端；容器化开发（docker-compose.dev.yml）通过
// VITE_PROXY_TARGET 指定 compose 内后端服务名，例如 http://backend:8000
const proxyTarget = process.env.VITE_PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
})
