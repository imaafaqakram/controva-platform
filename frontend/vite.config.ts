import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '^/(health|login|search|jobs|leads|pipeline|outreach|analytics|seo|competitors|people|social|ecommerce|product-hunt|config|intent|mockups)': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      }
    }
  }
})
