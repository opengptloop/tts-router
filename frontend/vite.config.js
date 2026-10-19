import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies API + WebSocket traffic to the backend so the
// frontend works the same locally and behind a reverse proxy in the cloud.
// Override the target with VITE_API_TARGET (e.g. http://backend:8000).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_API_TARGET || 'http://127.0.0.1:8000'

  return {
    plugins: [react()],
    server: {
      host: true,
      port: 5173,
      proxy: {
        '/api': { target, changeOrigin: true },
        '/v1': { target, changeOrigin: true },
        '/ws': { target, ws: true, changeOrigin: true },
      },
    },
    preview: {
      host: true,
      port: 4173,
      proxy: {
        '/api': { target, changeOrigin: true },
        '/v1': { target, changeOrigin: true },
        '/ws': { target, ws: true, changeOrigin: true },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
    },
  }
})
