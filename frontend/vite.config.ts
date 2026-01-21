import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/auth': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/cases': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/documents': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/folders': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/jobs': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/analyze': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/users': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/teams': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/firms': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/my': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/analysis-runs': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/generate_tracks': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/analyze_claims': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/analyze_with_tracks': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    minify: 'terser',
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          ui: ['framer-motion', 'lucide-react'],
        },
      },
    },
  },
})
