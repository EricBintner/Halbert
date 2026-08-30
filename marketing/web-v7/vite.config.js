import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'path';

export default defineConfig({
  plugins: [
    tailwindcss(),
    react(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@tokens': path.resolve(__dirname, './shared-tokens'),
      '@halbert/design-system': path.resolve(__dirname, '../../packages/design-system/src'),
    },
  },
  server: {
    port: 5180,
    host: true,
  },
});
