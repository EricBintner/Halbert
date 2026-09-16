// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import type { Preview, Decorator } from '@storybook/react'
import { DocsContainer, type DocsContainerProps } from '@storybook/blocks'
import { create } from '@storybook/theming'
import { GLOBALS_UPDATED } from 'storybook/internal/core-events'

import { readInjectedThemes } from './theme'

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

/**
 * Docs pages (autodocs, MDX) are styled by Storybook's own docs theme, not by
 * the token file, so they need the same light/dark pair the manager uses and
 * they need to follow the toolbar toggle. The store is not on the public
 * context type, hence the narrow cast for the initial value; updates arrive
 * on the channel.
 */
const injected = readInjectedThemes()
const docsThemes = { light: create(injected.light), dark: create(injected.dark) }

type ThemeName = keyof typeof docsThemes
const themeOf = (globals?: { theme?: unknown }): ThemeName => (globals?.theme === 'dark' ? 'dark' : 'light')

function initialTheme(context: DocsContainerProps['context']): ThemeName {
  const store = (context as unknown as { store?: { userGlobals?: { globals?: { theme?: unknown } } } }).store
  return themeOf(store?.userGlobals?.globals)
}

const ThemedDocsContainer = ({ context, children }: React.PropsWithChildren<DocsContainerProps>) => {
  const [theme, setTheme] = React.useState<ThemeName>(() => initialTheme(context))
  React.useEffect(() => {
    const onGlobals = ({ globals }: { globals?: { theme?: unknown } }) => setTheme(themeOf(globals))
    context.channel.on(GLOBALS_UPDATED, onGlobals)
    return () => context.channel.off(GLOBALS_UPDATED, onGlobals)
  }, [context])
  return (
    <DocsContainer context={context} theme={docsThemes[theme]}>
      {children}
    </DocsContainer>
  )
}

const preview: Preview = {
  parameters: {
    controls: { matchers: { color: /(background|color)$/i, date: /Date$/i } },
    backgrounds: { disable: true },
    docs: { container: ThemedDocsContainer },
    options: {
      storySort: {
        order: ['Brand', 'Design Tokens', 'Primitives', 'Instruments', 'Surfaces', 'Modules', 'Agent', 'Voice', 'Drafts'],
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
