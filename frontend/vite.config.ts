import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The backend is proxied so the demo runs from one origin and there is no CORS
// story to explain on stage.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true,
                rewrite: (p) => p.replace(/^\/api/, '') },
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
})
