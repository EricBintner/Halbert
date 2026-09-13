// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * PairingQRCode: the code carries the host URL, the PIN stays out, and
 * a loopback origin says so honestly.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PairingQRCode } from './PairingQRCode'

vi.mock('qrcode', () => ({
  default: {
    toCanvas: vi.fn(async () => undefined),
  },
}))

describe('PairingQRCode', () => {
  it('encodes the host URL — and nothing else', async () => {
    const QRCode = (await import('qrcode')).default
    render(<PairingQRCode url="http://mac-mini.local:8000" />)
    expect(QRCode.toCanvas).toHaveBeenCalledWith(
      expect.anything(),
      'http://mac-mini.local:8000',
      expect.anything(),
    )
    // No PIN, no request_id, no token — the URL is the whole payload.
    const payload = (QRCode.toCanvas as ReturnType<typeof vi.fn>).mock.calls[0][1]
    expect(payload).not.toMatch(/pin|token|request_id/i)
  })

  it('shows the URL in plain text for the manual path', () => {
    render(<PairingQRCode url="http://mac-mini.local:8000" />)
    expect(screen.getByText('http://mac-mini.local:8000')).toBeInTheDocument()
  })

  it('warns when the origin is loopback', () => {
    render(<PairingQRCode url="http://localhost:8000" />)
    expect(screen.getByText(/loopback address/)).toBeInTheDocument()
  })

  it('says the PIN is never inside the code', () => {
    render(<PairingQRCode url="http://mac-mini.local:8000" />)
    expect(screen.getByText(/PIN is never inside the code/)).toBeInTheDocument()
  })
})
