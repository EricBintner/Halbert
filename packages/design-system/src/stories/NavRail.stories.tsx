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
    header: (
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

export const SideBySide: StoryObj = {
  render: () => (
    <>
      <Note>
        The dashboard rail (left) and the settings rail (right) are the same component.
        Section labels, item type, weight, tracking, spacing, active treatment and icon
        colour all come from one stylesheet, so they cannot drift.
      </Note>
      <div style={{ height: '60vh', display: 'flex', border: '1px solid var(--color-line)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
        <NavRail
          sections={dashboardSections}
          activeId="dashboard"
          onSelect={() => {}}
        />
        <NavRail
          sections={[
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
          ]}
          activeId="being"
          tabMode
          searchable
          searchPlaceholder="Filter settings…"
          header={
            <button type="button" onClick={() => {}} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', width: '100%', padding: 'var(--space-2) var(--space-3)', border: 'none', background: 'none', color: 'var(--color-ink-secondary)', fontFamily: 'var(--font-sans)', fontSize: 12, fontWeight: 500, cursor: 'pointer' }}>
              <ArrowLeftIcon className="hb-navrail__icon" />
              Back
            </button>
          }
          onSelect={() => {}}
        />
      </div>
    </>
  ),
}
