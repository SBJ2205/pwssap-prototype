import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: [
      'sustainability-economies-each-regarding.trycloudflare.com',
      '.trycloudflare.com'
    ],
    proxy: {
      '/admin': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/semesters': 'http://localhost:8000',
      '/students': 'http://localhost:8000',
      '/subjects': 'http://localhost:8000',
      '/teachers': 'http://localhost:8000',
      '/timeslots': 'http://localhost:8000'
    }
  }
})
