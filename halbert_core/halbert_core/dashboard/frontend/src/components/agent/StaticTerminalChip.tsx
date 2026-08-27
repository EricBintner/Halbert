// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * StaticTerminalChip — the record of a terminal the page no longer holds.
 *
 * A stored turn remembers the ids of the terminals it opened; after a reload
 * the live store does not have them (Plan A stores ids, not output — Plan B
 * stores blocks). The chip keeps the spot in the transcript honest: a
 * terminal ran here, and it has ended. Copy is state-based, never a hash.
 */

interface StaticTerminalChipProps {
  id: string;
  /** Command line, when known. */
  label?: string;
}

export function StaticTerminalChip({ id, label }: StaticTerminalChipProps) {
  return (
    <span
      data-session-id={id}
      title="This terminal ended before the page loaded"
      className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-canvas-subtle px-2 py-0.5 text-[11px] font-mono text-ink-secondary"
    >
      <span>terminal · ended</span>
      {label && <span className="truncate max-w-[12rem] text-ink-tertiary">{label}</span>}
    </span>
  );
}

export default StaticTerminalChip;
