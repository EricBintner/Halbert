// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { StorybookConfig } from '@storybook/react-vite'

import { parseTokens } from './tokens'
import { INJECTED_GLOBAL, buildThemes, parseMarkSvg } from './theme'

// This file is loaded through esbuild-register as CommonJS, so __dirname is
// the config directory. tokens.css and the brand assets live at the repo root.
const REPO_ROOT = resolve(__dirname, '../../..')
const read = (rel: string) => readFileSync(resolve(REPO_ROOT, rel), 'utf8')

const tokens = parseTokens(read('shared-tokens/tokens.css'))
const themes = buildThemes(tokens, parseMarkSvg(read('assets/brand/halbert-mark-7lines.svg')))

// The themes travel to both documents as build-time JSON; no runtime file
// holds a colour. "</" is escaped so the brand-line markup cannot close the tag.
const themeScript = `<script>globalThis.${INJECTED_GLOBAL} = ${JSON.stringify(themes).replace(/<\//g, '<\\/')};</script>`
const themeColorMeta =
  `<meta name="theme-color" media="(prefers-color-scheme: light)" content="${tokens.light['--color-canvas']}">` +
  `<meta name="theme-color" media="(prefers-color-scheme: dark)" content="${tokens.dark['--color-canvas']}">`

const config: StorybookConfig = {
  stories: ['../src/**/*.mdx', '../src/**/*.stories.@(ts|tsx)'],
  addons: [
    '@storybook/addon-essentials',
    // The brand's accessibility gate covers colour pairs in the token file;
    // this covers the other half — roles, names, and contrast as rendered.
    '@storybook/addon-a11y',
  ],
  framework: {
    name: '@storybook/react-vite',
    options: {},
  },
  core: { disableTelemetry: true },
  managerHead: (head) => `${head ?? ''}\n${themeColorMeta}\n${themeScript}`,
  previewHead: (head) => `${head ?? ''}\n${themeScript}`,
  viteFinal: async (config) => {
    // tokens.css lives at the repo root, two levels above this package.
    config.server ??= {}
    config.server.fs ??= {}
    config.server.fs.allow = ['../..', ...(config.server.fs.allow ?? [])]
    return config
  },
}

export default config
