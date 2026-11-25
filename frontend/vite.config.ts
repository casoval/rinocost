import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// En desarrollo, todo lo que empiece con /api se reenvía a FastAPI (sin problemas de CORS).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (ruta) => ruta.replace(/^\/api/, ''),
      },
    },
  },
});
