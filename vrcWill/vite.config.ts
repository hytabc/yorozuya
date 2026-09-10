import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  plugins: [svelte()],
  resolve: {
    alias: {
      $lib: fileURLToPath(new URL('./src/lib', import.meta.url)),
      $data: fileURLToPath(new URL('./src/lib/data', import.meta.url)),
    },
  },
  build: {
    target: 'es2022',
    // 首包预算 < 300KB (gzip)，见 PRD §7.4
    chunkSizeWarningLimit: 300,
    rollupOptions: {
      output: {
        manualChunks: {
          // 关卡数据按章节拆分，配合路由懒加载
          'data-ch1': ['./src/lib/data/levels/1-1.json', './src/lib/data/levels/1-2.json', './src/lib/data/levels/1-3.json'],
        },
      },
    },
  },
  server: {
    port: 5173,
    open: true,
  },
});
