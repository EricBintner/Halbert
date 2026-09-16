// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    // Stylesheets are not processed in tests — except a `?raw` import, which
    // is text, not CSS: the Storybook theme test reads tokens.css that way.
    // `css: false` would blank it too, because vitest matches on the `.css`
    // extension before looking at the query.
    css: { include: [/\?raw$/] },
  },
})
