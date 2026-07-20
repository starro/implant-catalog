import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  build: { outDir: 'dist', emptyOutDir: true },
  // 개발 중에는 API 를 3000번 UI 서버로 프록시한다.
  server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:3000' } },
});
