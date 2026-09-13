// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * PairingQRCode — the QR the phone scans to find this host.
 *
 * The QR encodes the host URL and nothing more (companion handoff §7.3):
 * the phone learns where the mind lives, then runs the ordinary
 * pair → PIN → verify flow. The PIN stays out of the QR on purpose —
 * reading it off this screen is the physical-presence boundary that
 * keeps pairing from being a network-only act.
 *
 * The URL is whatever origin served the dashboard. When that origin is
 * loopback (the kiosk), the QR would hand the phone a useless address —
 * the card says so and shows the URL plainly for the Tailscale/manual
 * path.
 */
import { useEffect, useRef, useState } from 'react'
import QRCode from 'qrcode'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

function isLoopback(url: string): boolean {
  try {
    const host = new URL(url).hostname
    return host === 'localhost' || host === '127.0.0.1' || host === '::1'
  } catch {
    return false
  }
}

export function PairingQRCode({ url }: { url?: string }) {
  const target = url ?? (typeof window !== 'undefined' ? window.location.origin : '')
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [failed, setFailed] = useState(false)
  const loopback = isLoopback(target)

  useEffect(() => {
    if (!target || !canvasRef.current) return
    QRCode.toCanvas(canvasRef.current, target, {
      margin: 1,
      width: 160,
      errorCorrectionLevel: 'M',
    }).catch(() => setFailed(true))
  }, [target])

  return (
    <Card>
      <CardHeader className="space-y-1.5">
        <CardTitle className="text-sm">Pair a device by QR</CardTitle>
        <CardDescription>
          Point the companion app at this code, then complete pairing with
          the PIN shown here — the PIN is never inside the code.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {failed ? (
          <p className="text-sm text-muted-foreground">
            Could not render the code — use the address below instead.
          </p>
        ) : (
          <canvas ref={canvasRef} aria-label={`Pairing QR code for ${target}`} />
        )}
        <p className="text-xs text-muted-foreground break-all">{target}</p>
        {loopback && (
          <p className="text-xs text-muted-foreground">
            This code carries a loopback address only the machine itself can
            reach. For a phone on the network, open the dashboard through
            this machine's LAN address and pair from there — or use the
            manual link flow.
          </p>
        )}
      </CardContent>
    </Card>
  )
}
