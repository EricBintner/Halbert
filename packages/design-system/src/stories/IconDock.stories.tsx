// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import type { Meta, StoryObj } from '@storybook/react'

import { IconDock, type IconDockItem } from '../surfaces/IconDock'
import { GitHubIcon, StorybookIcon, XIcon, RedditIcon } from '../icons/brands'

/** Generic 16px stroke glyphs for the action examples (lucide paths). */
const Icon = (d: string) =>
  function StrokeIcon({ className }: { className?: string }) {
    return (
      <svg
        className={className}
        width={16}
        height={16}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d={d} />
      </svg>
    )
  }
const RefreshIcon = Icon('M21 12a9 9 0 1 1-2.64-6.36M21 3v6h-6')
const SunIcon = Icon(
  'M12 3v2M12 19v2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M3 12h2M19 12h2M5.6 18.4 7 17M17 7l1.4-1.4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z',
)

/** The marketing set: two live links, two placeholders until the accounts exist. */
const corner: IconDockItem[] = [
  { id: 'github', label: 'GitHub', icon: GitHubIcon, href: 'https://github.com/EricBintner/Halbert' },
  { id: 'storybook', label: 'Storybook', icon: StorybookIcon, href: 'https://storybook.halbert.computer' },
  { id: 'x', label: 'X', icon: XIcon, disabled: true },
  { id: 'reddit', label: 'Reddit', icon: RedditIcon, disabled: true },
]

const meta: Meta<typeof IconDock> = {
  title: 'Surfaces/IconDock',
  tags: ['autodocs'],
  component: IconDock,
  parameters: {
    layout: 'centered',
    docs: {
      description: {
        component:
          'A bare row of icon-only links or actions. The glyphs inherit their ink from the parent, so a consumer can paint a masked second copy in another ink — the marketing site inverts the dock where the vermilion stroke passes under it, like its header logo. Disabled items are real disabled buttons: named, dimmed, out of the tab order, with a "coming soon" tooltip.',
      },
    },
  },
  args: { items: corner, label: 'Links', orientation: 'horizontal' },
  argTypes: {
    orientation: { control: 'inline-radio', options: ['horizontal', 'vertical'] },
    items: { control: false },
  },
}
export default meta
type Story = StoryObj<typeof IconDock>

/** GitHub and Storybook live; X and Reddit placeholders. */
export const MarketingCorner: Story = {}

export const AllEnabled: Story = {
  args: {
    items: corner.map((item) =>
      item.disabled ? { ...item, disabled: false, href: `https://example.com/${item.id}` } : item,
    ),
  },
}

export const Vertical: Story = {
  args: { orientation: 'vertical' },
}

/** Buttons instead of links: the same plate as an action cluster. */
export const Actions: Story = {
  args: {
    label: 'Canvas tools',
    items: [
      { id: 'refresh', label: 'Refresh readings', icon: RefreshIcon, onClick: () => undefined },
      { id: 'daylight', label: 'Daylight', icon: SunIcon, onClick: () => undefined },
    ],
  },
}
