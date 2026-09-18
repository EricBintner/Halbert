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
      // Dossier data (plan §6 Step 2/3): one copy of each dataset, aliased
      // across both marketing sites, never duplicated. feature-reference
      // uses the same two aliases from its own config.
      '@halbert/shared': path.resolve(__dirname, '../shared'),
      '@halbert/catalog': path.resolve(__dirname, '../feature-reference/src/catalog.json'),
    },
  },
  build: {
    rollupOptions: {
      // The legal pages are entries, not public/ files: they import the token
      // dictionary through src/legal.css, so they must go through the build.
      input: {
        main: path.resolve(__dirname, 'index.html'),
        privacy: path.resolve(__dirname, 'privacy.html'),
        terms: path.resolve(__dirname, 'terms.html'),
      },
    },
  },
  server: {
    port: 5188,
    host: true,
  },
});
