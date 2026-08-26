// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import type { StorybookConfig } from '@storybook/react-vite'

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
  viteFinal: async (config) => {
    // tokens.css lives at the repo root, two levels above this package.
    config.server ??= {}
    config.server.fs ??= {}
    config.server.fs.allow = ['../..', ...(config.server.fs.allow ?? [])]
    return config
  },
}

export default config
