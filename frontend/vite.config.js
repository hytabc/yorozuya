import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 本地开发默认直连本机后端；容器化开发（docker-compose.dev.yml）通过
// VITE_PROXY_TARGET 指定 compose 内后端服务名，例如 http://backend:8000
const proxyTarget = process.env.VITE_PROXY_TARGET || 'http://localhost:8000'

// Vite dev server 的 Host 校验白名单：默认只允许 localhost。
// 通过 FRP / 反向代理对外提供访问时，用 VITE_ALLOWED_HOSTS（逗号分隔）放行外部域名，
// 例如 docker-compose.dev.yml 里注入 VITE_ALLOWED_HOSTS=${FRP_SERVER_ADDR}。
const envHosts = (process.env.VITE_ALLOWED_HOSTS || '')
  .split(',')
  .map((host) => host.trim())
  .filter(Boolean)

export default defineConfig({
  plugins: [vue()],
  server: {
    strictPort: true,
    watch: {
      usePolling: process.env.VITE_USE_POLLING === 'true',
    },
    allowedHosts: ['localhost', '127.0.0.1', '::1', ...envHosts],
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
})
