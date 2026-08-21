import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    // 开发期把 /api 代理到本地 Python 服务，避免浏览器跨源。
    proxy: {
      "/api": "http://127.0.0.1:8765",
    },
  },
})
