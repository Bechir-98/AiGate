import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/scan': 'http://localhost:8000',
      '/anonymize': 'http://localhost:8000',
      '/deanonymize': 'http://localhost:8000',
      '/mappings': 'http://localhost:8000',
      '/gateway': 'http://localhost:8000',
      '/config': 'http://localhost:8000',
    },
  },
})
