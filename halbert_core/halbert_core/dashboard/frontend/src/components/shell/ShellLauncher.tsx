// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ShellLauncher — the admin's way to open a terminal of their own.
 *
 * This affordance used to live in TerminalAccordionDock, which the tasks
 * column replaced. The accordion carried the only launcher on the page, so
 * replacing it without one would have removed the ability to open a shell at
 * all — silently, as a side effect of a layout change.
 *
 * A failure is said out loud. The pool has a cap and the session manager has
 * a ceiling, so "nothing happened" is a real outcome, and a button that does
 * nothing is indistinguishable from a broken one.
 */

import { useState, type ReactNode } from 'react';
import { useTerminalSessions } from '../../hooks/useTerminalSessions';

/** An interactive login shell. /bin/sh -c runs it, so the child expands
 *  $SHELL; the fallback keeps this working where $SHELL is not exported. */
const NEW_SHELL_COMMAND = 'exec "${SHELL:-/bin/bash}" -i';

export function ShellLauncher(): ReactNode {
  const { spawn } = useTerminalSessions();
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const open = async () => {
    setLaunching(true);
    setError(null);
    try {
      await spawn(NEW_SHELL_COMMAND);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLaunching(false);
    }
  };

  return (
    <div className="space-y-1" data-shell-launcher>
      <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
        Your shell
      </div>
      <button
        type="button"
        onClick={open}
        disabled={launching}
        aria-label="Open a shell"
        className="text-[10px] text-muted-foreground hover:text-text border border-hairline rounded px-1.5 py-0.5 disabled:opacity-50"
      >
        {launching ? 'opening…' : 'Open a shell'}
      </button>
      {error && (
        <div role="status" className="text-[10px] text-status-critical">
          {error}
        </div>
      )}
    </div>
  );
}

export default ShellLauncher;
