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
      '@tokens': path.resolve(__dirname, '../../shared-tokens'),
      '@halbert/design-system': path.resolve(__dirname, '../../packages/design-system/src'),
      // Dossier data (plan §6 Step 2/3): one copy of each dataset, aliased
      // across both marketing sites, never duplicated. web-v10 uses the same
      // two aliases from its own config.
      '@halbert/shared': path.resolve(__dirname, '../shared'),
      '@halbert/catalog': path.resolve(__dirname, './src/catalog.json'),
    },
  },
  server: {
    // 5188 collides with web-v10's dev port (launch.json runs web-v10 on
    // 5189 via CLI override). This site takes 5190.
    port: 5190,
    host: true,
  },
});