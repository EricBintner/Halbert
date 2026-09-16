// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import type { Meta, StoryObj } from '@storybook/react'

import { NavRail, type NavRailSection } from '../surfaces/NavRail'

const Note = ({ children }: { children: React.ReactNode }) => (
  <p style={{ color: 'var(--color-ink-secondary)', fontSize: 13, maxWidth: '68ch', marginTop: 0 }}>{children}</p>
)

/* A couple of stand-in icon components so the story does not pull in lucide
 * (the library is dependency-free by contract). */
const Icon = (paths: string) => {
  const C = ({ className }: { className?: string }) => (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={paths} />
    </svg>
  )
  return C
}

const DashboardIcon = Icon('M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z')
const ServerIcon = Icon('M4 5h16v6H4zM4 13h16v6H4z')
const ShieldIcon = Icon('M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z')
const GearIcon = Icon('M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12a7 7 0 0 0-.1-1l2-1.5-2-3.5-2.4 1a7 7 0 0 0-1.7-1L14.5 2h-5l-.3 2.5a7 7 0 0 0-1.7 1l-2.4-1-2 3.5 2 1.5a7 7 0 0 0 0 2l-2 1.5 2 3.5 2.4-1a7 7 0 0 0 1.7 1l.3 2.5h5l.3-2.5a7 7 0 0 0 1.7-1l2.4 1 2-3.5-2-1.5c.1-.3.1-.7.1-1z')
const ArrowLeftIcon = Icon('M19 12H5M12 19l-7-7 7-7')

const meta: Meta<typeof NavRail> = {
  title: 'Surfaces/NavRail',
  tags: ['autodocs'],
  component: NavRail,
  parameters: { layout: 'fullscreen' },
}
export default meta

const dashboardSections: NavRailSection[] = [
  {
    id: 'overview',
    label: 'Overview',
    items: [
      { id: 'dashboard', label: 'Dashboard', icon: DashboardIcon },
      { id: 'home', label: 'Home', icon: DashboardIcon },
    ],
  },
  {
    id: 'system',
    label: 'System',
    items: [
      { id: 'services', label: 'Services', icon: ServerIcon },
      { id: 'storage', label: 'Storage', icon: ServerIcon },
      { id: 'security', label: 'Security', icon: ShieldIcon },
    ],
  },
]

export const DashboardRail: StoryObj<typeof NavRail> = {
  args: {
    sections: dashboardSections,
    activeId: 'services',
    onSelect: () => {},
  },
  render: (args) => (
    <div style={{ height: '100vh', display: 'flex' }}>
      <NavRail {...args} />
      <div style={{ flex: 1, padding: 'var(--space-6)', color: 'var(--color-ink-secondary)' }}>
        Page content lives here.
      </div>
    </div>
  ),
}

export const SettingsRail: StoryObj<typeof NavRail> = {
  args: {
    sections: [
      {
        id: 'personality',
        label: 'Personality',
        items: [{ id: 'being', label: 'Identity & Voice', icon: GearIcon }],
      },
      {
        id: 'intelligence',
        label: 'Intelligence',
        items: [
          { id: 'ai', label: 'Models & Providers', icon: GearIcon },
          { id: 'knowledge', label: 'Knowledge', icon: GearIcon },
        ],
      },
      {
        id: 'developer',
        label: 'Developer',
        items: [{ id: 'debug', label: 'Debug', icon: GearIcon }],
      },
    ],
    activeId: 'ai',
    tabMode: true,
    searchable: true,
    searchPlaceholder: 'Filter settings…',
    /* Footer, not header: this rail is laid over the dashboard rail, and the
     * dashboard rail's footer holds the settings gear. Same slot on both means
     * Back lands exactly where the gear was. */
    footer: (
      <button
        type="button"
        onClick={() => {}}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-2)',
          width: '100%',
          padding: 'var(--space-2) var(--space-3)',
          border: 'none',
          borderRadius: 'var(--radius-md)',
          background: 'none',
          color: 'var(--color-ink-secondary)',
          fontFamily: 'var(--font-sans)',
          fontSize: 12,
          fontWeight: 500,
          cursor: 'pointer',
        }}
      >
        <ArrowLeftIcon className="hb-navrail__icon" />
        Back
      </button>
    ),
    onSelect: () => {},
  },
  render: (args) => (
    <div style={{ height: '100vh', display: 'flex' }}>
      <NavRail {...args} />
      <div
        role="tabpanel"
        style={{ flex: 1, padding: 'var(--space-8)', color: 'var(--color-ink)' }}
      >
        <h2 style={{ marginTop: 0 }}>Models &amp; Providers</h2>
        <p style={{ color: 'var(--color-ink-secondary)' }}>
          The settings panel rail is the same component as the dashboard rail, so the
          typography is identical by construction — not by two people keeping two class
          strings in step.
        </p>
      </div>
    </div>
  ),
}

const railButtonStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-2)',
  width: '100%',
  padding: 'var(--space-2) var(--space-3)',
  border: 'none',
  borderRadius: 'var(--radius-md)',
  background: 'none',
  color: 'var(--color-ink-secondary)',
  fontFamily: 'var(--font-sans)',
  fontSize: 12,
  fontWeight: 500,
  cursor: 'pointer',
}

const settingsSections: NavRailSection[] = [
  {
    id: 'personality',
    label: 'Personality',
    items: [{ id: 'being', label: 'Identity & Voice', icon: GearIcon }],
  },
  {
    id: 'intelligence',
    label: 'Intelligence',
    items: [
      { id: 'ai', label: 'Models & Providers', icon: GearIcon },
      { id: 'knowledge', label: 'Knowledge', icon: GearIcon },
    ],
  },
]

/**
 * Settings does not sit beside the dashboard rail — it is laid over it.
 *
 * Toggle the story to watch the swap: the settings rail comes down on top of
 * the dashboard rail, and because both rails put their exit control in the
 * footer slot, the gear and Back occupy the same pixel.
 */
export const SettingsOverlay: StoryObj = {
  render: function SettingsOverlayStory() {
    const [open, setOpen] = React.useState(true)
    return (
      <>
        <Note>
          The settings rail is laid <strong>over</strong> the dashboard rail, not beside it —
          one column, not two. Both rails put their exit control in the same{' '}
          <code>footer</code> slot, so the gear that opens settings and the Back that
          closes it land on the same pixel and the change reads as one surface flipping.
        </Note>
        <div
          style={{
            position: 'relative',
            /* Tall enough that both rails show their whole item list; the
             * point of the story is the overlay, and a rail cropped to two
             * rows undersells it. */
            height: 440,
            display: 'flex',
            border: '1px solid var(--color-line)',
            borderRadius: 'var(--radius-lg)',
            overflow: 'hidden',
          }}
        >
          <NavRail
            sections={dashboardSections}
            activeId="dashboard"
            onSelect={() => {}}
            footer={
              <button type="button" style={railButtonStyle} onClick={() => setOpen(true)}>
                <GearIcon className="hb-navrail__icon" />
                Settings
              </button>
            }
          />

          <div style={{ flex: 1, padding: 'var(--space-6)', background: 'var(--color-surface)' }}>
            <Note>The dashboard underneath.</Note>
          </div>

          {open && (
            <div
              style={{
                position: 'absolute',
                inset: 0,
                zIndex: 20,
                display: 'flex',
                overflow: 'hidden',
                background: 'var(--color-surface)',
              }}
            >
              <NavRail
                sections={settingsSections}
                activeId="being"
                tabMode
                searchable
                searchPlaceholder="Filter settings…"
                onSelect={() => {}}
                footer={
                  <button type="button" style={railButtonStyle} onClick={() => setOpen(false)}>
                    <ArrowLeftIcon className="hb-navrail__icon" />
                    Back
                  </button>
                }
              />
              <div style={{ flex: 1, padding: 'var(--space-6)' }}>
                <Note>Settings, over the top. The conversation panel beside it is untouched.</Note>
              </div>
            </div>
          )}
        </div>
      </>
    )
  },
}
