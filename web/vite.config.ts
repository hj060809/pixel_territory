import { defineConfig } from 'vite';
import { resolve } from 'node:path';

// 개발: npm run dev (http://localhost:5173) — /api, /ws, /assets는 파이썬 서버(8000)로 넘긴다.
// 배포: npm run build → dist/ (파이썬 서버가 그대로 내보낸다)
export default defineConfig({
  build: {
    outDir: 'dist',
    assetsDir: 'static',            // /assets는 서버의 데모 지도 경로라서
    target: 'es2022',
    rollupOptions: {
      input: {
        index: resolve(__dirname, 'index.html'),
        viewer: resolve(__dirname, 'viewer.html'),
        parity: resolve(__dirname, 'parity.html'),
      },
    },
  },
  worker: { format: 'es' },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/assets': 'http://127.0.0.1:8000',
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
});
