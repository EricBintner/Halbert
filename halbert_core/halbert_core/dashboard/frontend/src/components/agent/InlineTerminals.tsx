// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * InlineTerminals — terminals flowing inside the conversation stream (E1d/E1f).
 *
 * A command Halbert runs appears where it was run: a live TerminalTile in the
 * message, not a transcript pasted in afterwards. Scroll it out of view and it
 * parks in the right-column accordion dock, leaving a TetherChip behind that
 * marks the spot and brings it back on click.
 *
 * Docking is deliberately sticky. Swapping a ~200px tile for a ~20px chip
 * changes the layout under the observer, so honouring every "back in view"
 * callback would flip the tile in and out on a single scroll. Docking is
 * therefore a one-way move that only the user undoes.
 */

import { useState } from 'react';
import { useTerminalSessions, type TerminalSession } from '../../hooks/useTerminalSessions';
import { useIntersectionDock } from '../../hooks/useIntersectionDock';
import { TerminalTile } from './TerminalTile';
import { TetherChip } from './TetherChip';
import { StaticTerminalChip } from './StaticTerminalChip';

interface InlineTerminalsProps {
  /** Terminal session ids opened during this turn, oldest first. */
  sessionIds: string[];
}

function InlineTerminal({ session }: { session: TerminalSession }) {
  const { setVisible } = useTerminalSessions();
  const [docked, setDocked] = useState(false);

  const { ref } = useIntersectionDock({
    onDock: () => {
      setDocked(true);
      // Release the live xterm slot so a terminal on screen can take it.
      setVisible(session.id, false);
    },
  });

  const undock = () => {
    setDocked(false);
    setVisible(session.id, true);
  };

  return (
    <div ref={ref as React.RefObject<HTMLDivElement>} data-terminal-origin={session.id}>
      {docked ? (
        <TetherChip
          sessionId={session.id}
          label={session.command}
          docked
          onClick={undock}
        />
      ) : (
        <TerminalTile session={session} />
      )}
    </div>
  );
}

export function InlineTerminals({ sessionIds }: InlineTerminalsProps) {
  const { sessions } = useTerminalSessions();
  if (sessionIds.length === 0) return null;

  const byId = new Map(sessions.map((s) => [s.id, s]));

  // An id the store does not know is a terminal that ended before this page
  // held it (reload, or a turn older than the store). It stays in the
  // transcript as a static chip; it is never dropped.
  return (
    <div className="space-y-2">
      {sessionIds.map((id) => {
        const session = byId.get(id);
        return session ? (
          <InlineTerminal key={id} session={session} />
        ) : (
          <StaticTerminalChip key={id} id={id} />
        );
      })}
    </div>
  );
}

export default InlineTerminals;
