// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { addons } from '@storybook/manager-api'
import { create } from '@storybook/theming'

/**
 * Storybook manager (chrome) branding.
 *
 * Paints the sidebar title bar in the Halbert brand: Olivetti Vermilion
 * accent on Bone canvas, with the title linking to the GitHub repo so a
 * visitor who lands on the public Storybook can find the source.
 */
const theme = create({
  base: 'light',
  brandTitle: 'Halbert Design System',
  brandUrl: 'https://github.com/EricBintner/Halbert',
  brandTarget: '_blank',
  colorPrimary: '#D34E24', // vermilion-600 — the identity stroke
  colorSecondary: '#C4451D', // vermilion-700 — accent-strong
  appBg: '#F7F4EE', // bone-100 — canvas
  appContentBg: '#FFFFFF',
  appBorderColor: '#E8E2D6',
  appBorderRadius: 4,
  textColor: '#1C1917', // graphite-900 — ink
  textInverseColor: '#F7F4EE',
  barBg: '#F7F4EE',
  barSelectedColor: '#D34E24',
  inputBg: '#FFFFFF',
  inputBorder: '#D6CFC0',
  inputTextColor: '#1C1917',
  fontBase: '"Nunito Sans", system-ui, -apple-system, sans-serif',
  fontCode: 'ui-monospace, "SF Mono", Menlo, monospace',
})

addons.setConfig({ theme })