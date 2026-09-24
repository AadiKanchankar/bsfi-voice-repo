import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The backend is proxied so the demo runs from one origin and there is no CORS
// story to explain on stage.
//
// The port is overridable so the end-to-end tests can bring up their own
// stack against a throwaway copy of the database, instead of driving whatever
// the presenter happens to have running.
const API_PORT = process.env.BFSI_API_PORT || '8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: `http://127.0.0.1:${API_PORT}`, changeOrigin: true,
                rewrite: (p) => p.replace(/^\/api/, '') },
      '/ws': { target: `ws://127.0.0.1:${API_PORT}`, ws: true },
    },
  },
})
