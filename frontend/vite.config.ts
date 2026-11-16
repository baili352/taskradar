import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 默认连接本机正式后端；隔离测试时可用 VITE_PROXY_TARGET 指向测试端口，
// 避免测试过程触碰正式数据库。
const proxyTarget =
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
    ?.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '127.0.0.1',
    proxy: {
      // 前端请求 /api 时转发到 FastAPI，避免跨域问题
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
})
