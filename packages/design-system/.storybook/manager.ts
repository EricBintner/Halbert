// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { addons } from '@storybook/manager-api'
import { create } from '@storybook/theming'
import { GLOBALS_UPDATED, SET_GLOBALS } from 'storybook/internal/core-events'

import { BRAND_NAME, readInjectedThemes } from './theme'

/**
 * Manager (chrome) branding.
 *
 * The two themes arrive from main.ts as injected JSON (see theme.ts). This
 * file applies the light one, then follows the Daylight / After hours global
 * so the sidebar changes with the canvas instead of staying bone while the
 * stories go charcoal.
 */
const injected = readInjectedThemes()
const themes = { light: create(injected.light), dark: create(injected.dark) }

addons.setConfig({ theme: themes.light })

const STOCK_SUFFIX = ' ⋅ Storybook'
const BRAND_SUFFIX = ` ⋅ ${BRAND_NAME}`

addons.register('halbert/chrome', (api) => {
  const follow = ({ globals }: { globals?: { theme?: unknown } }) => {
    api.setOptions({ theme: globals?.theme === 'dark' ? themes.dark : themes.light })
  }
  api.on(SET_GLOBALS, follow)
  api.on(GLOBALS_UPDATED, follow)

  // Storybook hardcodes the tab-title suffix in getDescription() and writes
  // its own <title> before any head injection, so the only seam is the node
  // itself. The observer writes only when the suffix is not already ours,
  // so its own write cannot re-trigger it.
  const title = document.querySelector('title')
  if (!title) return
  const rebrand = () => {
    const text = title.textContent ?? ''
    if (text.endsWith(STOCK_SUFFIX)) {
      title.textContent = text.slice(0, -STOCK_SUFFIX.length) + BRAND_SUFFIX
    } else if (text === 'Storybook' || text.endsWith('- Storybook')) {
      title.textContent = BRAND_NAME
    }
  }
  rebrand()
  new MutationObserver(rebrand).observe(title, { childList: true, characterData: true, subtree: true })
})
