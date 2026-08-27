// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The `/model status` diagnostic card.
 *
 * Ephemeral and local to the composer: it answers a command the user typed and
 * is never part of the conversation the agent sees.
 */
import type { ModelStatusLines } from '@/lib/slashCommands'

export function ModelStatusCard({ rows }: { rows: ModelStatusLines }) {
  return (
    <dl
      className="rounded-lg border border-border bg-card px-4 py-3 text-xs font-mono space-y-1"
      aria-label="Active model status"
    >
      {rows.map((row) => (
        <div key={row.label} className="flex gap-3">
          <dt className="w-36 shrink-0 text-muted-foreground">{row.label}</dt>
          <dd className="text-foreground break-all">{row.value}</dd>
        </div>
      ))}
    </dl>
  )
}
