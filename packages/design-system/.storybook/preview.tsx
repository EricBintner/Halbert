// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import type { Preview, Decorator } from '@storybook/react'

import '../src/styles.css'

/**
 * Theme decorator.
 *
 * Sets `data-theme` on the document element, which is exactly the switch the
 * token file listens for. Storybook's own `backgrounds` addon is disabled in
 * favour of this: painting a swatch behind the canvas would show the right
 * colour while leaving every token on its light value, which is how a "dark
 * mode" ships broken.
 */
const withTheme: Decorator = (Story, context) => {
  const theme = context.globals.theme ?? 'light'

  React.useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    return () => document.documentElement.removeAttribute('data-theme')
  }, [theme])

  return (
    <div
      style={{
        background: 'var(--color-canvas)',
        color: 'var(--color-ink)',
        fontFamily: 'var(--font-sans)',
        padding: 'var(--space-6)',
        minHeight: '100vh',
      }}
    >
      <Story />
    </div>
  )
}

const preview: Preview = {
  parameters: {
    controls: { matchers: { color: /(background|color)$/i, date: /Date$/i } },
    backgrounds: { disable: true },
    options: {
      storySort: {
        order: ['Design Tokens', 'Primitives', 'Surfaces', 'Modules'],
      },
    },
  },
  globalTypes: {
    theme: {
      description: 'Olivetti daylight or after hours',
      defaultValue: 'light',
      toolbar: {
        title: 'Theme',
        icon: 'circlehollow',
        items: [
          { value: 'light', icon: 'sun', title: 'Daylight' },
          { value: 'dark', icon: 'moon', title: 'After hours' },
        ],
        dynamicTitle: true,
      },
    },
  },
  decorators: [withTheme],
}

export default preview
