// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * HostShell — the conversation surface: you and the machine, side by side.
 *
 * Left: the continuous conversation spine (AgentChat). Right: the context
 * stage — live vitals and the terminal accordion dock.
 *
 * In the 3-panel shell, HostShell renders in the right panel. When the
 * center panel is also visible (side-by-side mode), the right panel is
 * narrow — pass `compact` to hide the context stage and give the
 * conversation the full panel width. When the center is hidden (Host
 * Focus), the right panel takes the full remaining width and the context
 * stage is shown.
 *
 * The engine for all of this (async PTYs, the WebSocket bridge, the
 * terminal store) already existed; what was missing was a shell that
 * mounted it. This is that shell.
 */

import { useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { AgentChat } from '../agent/AgentChat';
import { useShellMode } from '@/contexts/ShellModeContext';
import { ContextStage } from './ContextStage';
import { LiveRegion } from './LiveRegion';

/**
 * Where the model picker's "All models and endpoints…" link goes. The
 * settings page renders in the center panel, so this is a mode change
 * (ensure center is visible) and a navigation.
 */
const MODEL_SETTINGS_ROUTE = '/settings?tab=ai';

interface HostShellProps {
  /** When true, hide the context stage — the panel is too narrow. */
  compact?: boolean;
}

export function HostShell({ compact = false }: HostShellProps = {}) {
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
   * Open the full model configuration in the center panel. Navigating
   * without the mode change lands on a route that the right panel does
   * not render, which looks to the user like the link did nothing.
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
        className="flex-1 min-w-0 flex flex-col bg-background"
        aria-label="Conversation"
      >
        <AgentChat
          className="h-full"
          onOpenModelSettings={openModelSettings}
          onRunCommand={handleRunCommand}
        />
      </div>

      {/* Context stage — hidden in compact mode (side-by-side) where the
          panel is too narrow. In full mode (Host Focus), it takes half the
          surface on a wide window, never a strip. */}
      {!compact && (
        <aside
          className="hidden md:flex w-1/2 max-w-[640px] min-w-[320px] shrink-0 border-l border-border"
          aria-label="Context stage"
        >
          <ContextStage className="w-full" onJumpToTerminal={jumpToTerminal} />
        </aside>
      )}
    </div>
  );
}

export default HostShell;
