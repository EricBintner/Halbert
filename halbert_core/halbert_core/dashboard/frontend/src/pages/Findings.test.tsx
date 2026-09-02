// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Findings page tests (FE-15 audit cleanup) — covers the security
 * findings list loaded from GET /api/discoveries/?type=security: the
 * empty "No Findings Yet" state, per-item icon/detail rendering (SSH
 * issues, sudo users), the stat tiles, and the Scan button's round trip
 * through POST /api/discoveries/scan back to a reload.
 */
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Findings } from './Findings'

interface FindingItem {
  id: string
  name: string
  title: string
  description: string
  status: string
  severity: string
  data: Record<string, unknown>
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response
}

const FINDINGS: FindingItem[] = [
  {
    id: 'ssh-1',
    name: 'ssh-config',
    title: 'SSH Configuration',
    description: 'Password authentication is enabled.',
    status: 'Warning',
    severity: 'warning',
    data: { issues: ['Password authentication enabled', 'Root login allowed'] },
  },
  {
    id: 'sudo-1',
    name: 'sudo-users',
    title: 'Sudo Users',
    description: 'Accounts with elevated privileges.',
    status: 'Secure',
    severity: 'success',
    data: { users: ['eric', 'admin', 'ops', 'backup', 'ci', 'extra'] },
  },
  {
    id: 'f2b-1',
    name: 'fail2ban-status',
    title: 'fail2ban',
    description: 'Brute-force protection is active.',
    status: 'Active',
    severity: 'success',
    data: {},
  },
  {
    id: 'upd-1',
    name: 'auto-updates',
    title: 'Automatic Updates',
    description: 'Unattended security updates are disabled.',
    status: 'Disabled',
    severity: 'critical',
    data: {},
  },
]

/** Route /api/discoveries traffic; `state` is mutable so a scan's reload
 * can return different data (like the real backend after a rescan). */
function renderFindings(discoveries: FindingItem[]) {
  let state = discoveries
  const calls: Array<{ url: string; init?: RequestInit }> = []
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    if (url.startsWith('/api/discoveries/scan')) {
      return jsonResponse({ status: 'ok' })
    }
    if (url.startsWith('/api/discoveries/')) {
      return jsonResponse({ discoveries: state })
    }
    return jsonResponse({}, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<Findings />)
  return {
    calls,
    setNextLoad: (next: FindingItem[]) => {
      state = next
    },
  }
}

afterEach(() => vi.unstubAllGlobals())

describe('Findings', () => {
  it('shows the empty state with a Scan for Findings CTA when there are no findings', async () => {
    renderFindings([])
    expect(await screen.findByText('No Findings Yet')).toBeTruthy()
    expect(screen.getByText(/click scan to check your security configuration/i)).toBeTruthy()
    expect(screen.getByRole('button', { name: /scan for findings/i })).toBeTruthy()
  })

  it('renders findings with icons, descriptions, SSH issues, and a 5-user sudo slice', async () => {
    renderFindings(FINDINGS)
    expect(await screen.findByText('SSH Configuration')).toBeTruthy()
    expect(screen.getByText('Password authentication is enabled.')).toBeTruthy()
    expect(screen.getByText('Sudo Users')).toBeTruthy()
    expect(screen.getByText('fail2ban')).toBeTruthy()
    expect(screen.getByText('Automatic Updates')).toBeTruthy()

    // SSH detail rows (item.data.issues).
    expect(screen.getByText('Password authentication enabled')).toBeTruthy()
    expect(screen.getByText('Root login allowed')).toBeTruthy()

    // Sudo user badges are sliced to the first 5 of 6.
    expect(screen.getByText('eric')).toBeTruthy()
    expect(screen.getByText('ci')).toBeTruthy()
    expect(screen.queryByText('extra')).toBeNull()
  })

  it('computes the stat tiles from the findings severities', async () => {
    renderFindings(FINDINGS)
    await screen.findByText('SSH Configuration')

    expect(screen.getByText('Total Checks').nextElementSibling?.textContent).toBe('4')
    // 'Secure' also appears as a per-finding StatusBadge label below the
    // stat tiles (one fixture finding has status: 'Secure') — the stat
    // tile's own label is the first match in DOM order.
    expect(screen.getAllByText('Secure')[0].nextElementSibling?.textContent).toBe('2')
    expect(screen.getByText('Warnings').nextElementSibling?.textContent).toBe('1')
    expect(screen.getByText('Issues').nextElementSibling?.textContent).toBe('1')
  })

  it('renders a mention/chat action and a status badge for each finding', async () => {
    renderFindings(FINDINGS)
    await screen.findByText('SSH Configuration')

    expect(screen.getByTitle('Mention SSH Configuration in chat')).toBeTruthy()
    expect(screen.getByTitle('Chat about SSH Configuration')).toBeTruthy()
    // StatusBadge renders the raw status text.
    expect(screen.getByText('Warning')).toBeTruthy()
  })

  it('the empty-state Scan button posts a scan and reloads the findings', async () => {
    const user = userEvent.setup()
    const { calls, setNextLoad } = renderFindings([])
    await screen.findByText('No Findings Yet')
    setNextLoad(FINDINGS)

    await user.click(screen.getByRole('button', { name: /scan for findings/i }))

    await screen.findByText('SSH Configuration')
    const scanCall = calls.find((c) => c.url.startsWith('/api/discoveries/scan'))
    expect(scanCall).toBeTruthy()
    expect(JSON.parse(String(scanCall?.init?.body))).toEqual({ scan_type: 'security' })
    // A GET reload followed the scan.
    expect(calls.filter((c) => c.url.startsWith('/api/discoveries/?')).length).toBeGreaterThanOrEqual(2)
  })

  it('the header Scan button re-scans and reloads without duplicating the empty state', async () => {
    const user = userEvent.setup()
    const { calls, setNextLoad } = renderFindings(FINDINGS)
    await screen.findByText('SSH Configuration')
    setNextLoad(FINDINGS)

    await user.click(screen.getByRole('button', { name: /^scan$/i }))

    await waitFor(() =>
      expect(calls.some((c) => c.url.startsWith('/api/discoveries/scan'))).toBe(true),
    )
    // Findings are still shown after the reload — no crash into the empty state.
    expect(screen.getByText('SSH Configuration')).toBeTruthy()
  })

  it('the AI analysis panel Analyze button is disabled when there are no findings', async () => {
    renderFindings([])
    await screen.findByText('No Findings Yet')
    expect(screen.getByRole('button', { name: /^analyze$/i })).toBeDisabled()
  })

  it('the AI analysis panel Analyze button is enabled once findings load', async () => {
    renderFindings(FINDINGS)
    await screen.findByText('SSH Configuration')
    expect(screen.getByRole('button', { name: /^analyze$/i })).toBeEnabled()
  })
})
