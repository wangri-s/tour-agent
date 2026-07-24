import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    proxy: {
      '/chat': 'http://127.0.0.1:8002',
      '/chat/stream': 'http://127.0.0.1:8002',
      '/health': 'http://127.0.0.1:8002',
      '/admin': 'http://127.0.0.1:8002'
    }
  }
})
