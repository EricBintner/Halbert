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
import { useNavigate } from 'react-router-dom';
import { AgentChat } from '../agent/AgentChat';
import { useShellMode } from '@/contexts/ShellModeContext';
import { ContextStage } from './ContextStage';
import { LiveRegion } from './LiveRegion';

/**
 * Where the model picker's "All models and endpoints…" link goes. The models
 * tab of the settings page, which lives in browsing mode — so this is a mode
 * change and a navigation, and the shell is the only component that owns both.
 */
const MODEL_SETTINGS_ROUTE = '/settings?tab=ai';

export function HostShell() {
  const conversationRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { setMode } = useShellMode();

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

  /**
   * Leave the engaged surface for the full model configuration. Navigating
   * without the mode change lands on a route that engaged mode does not
   * render, which looks to the user like the link did nothing.
   */
  const openModelSettings = useCallback(() => {
    setMode('both');
    navigate(MODEL_SETTINGS_ROUTE);
  }, [navigate, setMode]);

  /**
   * "Run in Terminal" buttons in code blocks dispatch this. Layout.tsx
   * already listens for `halbert:run-command` and stages the command in the
   * composer via runOnHost — so dispatching the event is the correct wiring.
   * Without this, the buttons in code blocks were inert in the host shell.
   *
   * Returns a resolved Promise to satisfy the RunCommand type signature;
   * the actual command is staged (not executed) by runOnHost.
   */
  const handleRunCommand = useCallback((command: string) => {
    window.dispatchEvent(new CustomEvent('halbert:run-command', { detail: { command } }));
    return Promise.resolve({});
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
        aria-label="Conversation"
      >
        <AgentChat
          className="h-full"
          onOpenModelSettings={openModelSettings}
          onRunCommand={handleRunCommand}
        />
      </div>

      {/* Context stage — half the surface on a wide window, never a strip */}
      <aside className="hidden md:flex w-1/2 max-w-[640px] min-w-[320px] shrink-0" aria-label="Context stage">
        <ContextStage className="w-full" onJumpToTerminal={jumpToTerminal} />
      </aside>
    </div>
  );
}

export default HostShell;
