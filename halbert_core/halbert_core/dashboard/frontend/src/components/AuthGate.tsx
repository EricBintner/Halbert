// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * SEC-1: what a browser sees when it has not been let in yet.
 *
 * Every backend route now requires a credential. In the desktop app the Rust
 * shell injects one, so this never renders. In a browser the credential is a
 * session cookie from /auth/enter, and without it the whole dashboard would
 * otherwise mount and then fail one panel at a time — a wall of red that tells
 * the user nothing about what to do.
 *
 * So: ask the one public endpoint whether we are through the door, and if not,
 * say plainly how to get in. The machine speaks for itself here, as it does
 * everywhere else.
 */
import { useEffect, useState } from 'react'
import { apiToken, apiUrl } from '@/lib/apiBase'

type Status = 'checking' | 'in' | 'out' | 'unreachable'

export function AuthGate({ children }: { children: React.ReactNode }) {
  // The desktop app carries an injected credential, so it is never locked out
  // and should not pay for a round trip before rendering.
  const [status, setStatus] = useState<Status>(apiToken() ? 'in' : 'checking')

  useEffect(() => {
    if (status !== 'checking') return
    let cancelled = false
    fetch(apiUrl('/auth/status'), { credentials: 'same-origin' })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => {
        if (!cancelled) setStatus(body?.authenticated ? 'in' : 'out')
      })
      .catch(() => {
        // The backend is not answering at all. That is a different problem from
        // being locked out, and telling the user to fetch a link would be wrong.
        if (!cancelled) setStatus('unreachable')
      })
    return () => {
      cancelled = true
    }
  }, [status])

  if (status === 'in' || status === 'unreachable') return <>{children}</>
  if (status === 'checking') return null

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-8">
      <div className="max-w-lg space-y-4">
        <h1 className="text-2xl font-semibold text-foreground">
          I don't know who you are yet.
        </h1>
        <p className="text-muted-foreground">
          I only answer callers I can identify — anything else running on this
          computer would otherwise be able to read my screen, open a terminal and
          change my configuration.
        </p>
        <p className="text-muted-foreground">
          Run this on the machine I'm on, then open the link it prints:
        </p>
        <pre className="overflow-x-auto rounded-md border border-border bg-muted p-3 text-sm text-foreground">
          <code>python3 -m halbert_core.dashboard.ticket</code>
        </pre>
        <p className="text-sm text-muted-foreground">
          The link works once and expires after five minutes. The desktop app
          doesn't need it — it lets itself in.
        </p>
      </div>
    </div>
  )
}
