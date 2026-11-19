import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// base: './' makes the built site work from any folder of a static web server.
// build.minify: false keeps the generated JavaScript readable, as requested.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    minify: false,
    sourcemap: true,
  },
});
