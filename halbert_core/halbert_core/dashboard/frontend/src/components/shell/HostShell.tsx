// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * HostShell — the engaged surface: you and the machine, side by side.
 *
 * Left: the continuous conversation spine (AgentChat promoted from a sidecar
 * panel to the primary canvas). Right: the context stage — live vitals and the
 * terminal accordion dock.
 *
 * The engine for all of this (async PTYs, the WebSocket bridge, somatic
 * blocks, the terminal store) already existed; what was missing was a shell
 * that mounted it. This is that shell.
 */

import { useCallback, useRef } from 'react';
import { AgentChat } from '../agent/AgentChat';
import { ContextStage } from './ContextStage';
import { LiveRegion } from './LiveRegion';

export function HostShell() {
  const conversationRef = useRef<HTMLDivElement>(null);

  /**
   * Scroll the conversation back to where a docked terminal was opened.
   * InlineTerminals stamps each origin with data-terminal-origin.
   */
  const jumpToTerminal = useCallback((sessionId: string) => {
    const root = conversationRef.current;
    if (!root) return;
    const origin = root.querySelector(`[data-terminal-origin="${CSS.escape(sessionId)}"]`);
    origin?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, []);

  return (
    <div className="flex h-full min-h-0 min-w-0">
      {/* One polite status region and one assertive alert region for the
          whole shell (design §11). */}
      <LiveRegion />
      {/* Conversation spine */}
      <div
        ref={conversationRef}
        className="flex-1 min-w-0 flex flex-col bg-background border-r border-border"
      >
        <AgentChat className="h-full" />
      </div>

      {/* Context stage — half the surface on a wide window, never a strip */}
      <aside className="hidden md:flex w-1/2 max-w-[640px] min-w-[320px] shrink-0">
        <ContextStage className="w-full" onJumpToTerminal={jumpToTerminal} />
      </aside>
    </div>
  );
}

export default HostShell;
