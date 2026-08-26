// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ContextStage — the right half of the engaged surface.
 *
 * Holds what the conversation is about rather than the conversation itself:
 * the host's live vitals at the top, the terminal accordion dock below it, and
 * (via the module registry) any dashboard module summoned into view. The dock
 * is always mounted — its idle state is the proof that the terminal nervous
 * system is up, which is exactly what an unconditional `return null` hid.
 */

import { TerminalAccordionDock } from '../agent/TerminalAccordionDock';
import { ProactiveEventsBadge } from '../agent/ProactiveEventsBadge';
import { ModuleRenderer } from '../ModuleRenderer';
import { HostVitals } from './HostVitals';

interface StagedModule {
  key: string;
  module: string;
  props: Record<string, unknown>;
}

interface ContextStageProps {
  /** Dashboard modules summoned into the stage (Cmd+K / conversation). */
  modules?: StagedModule[];
  /** Scroll the conversation back to a terminal's inline origin. */
  onJumpToTerminal?: (sessionId: string) => void;
  className?: string;
}

export function ContextStage({
  modules = [],
  onJumpToTerminal,
  className = '',
}: ContextStageProps) {
  return (
    <div className={`flex flex-col h-full min-h-0 bg-background ${className}`}>
      {/* Stage header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border shrink-0">
        <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Host
        </span>
        <div className="ml-auto">
          <ProactiveEventsBadge />
        </div>
      </div>

      {/* Vitals + summoned modules scroll; the dock stays pinned below. */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        <HostVitals />

        {modules.length > 0 && (
          <div className="px-3 pb-3 space-y-3 border-t border-border pt-3">
            {modules.map((m) => (
              <ModuleRenderer key={m.key} module={m.module} props={m.props} />
            ))}
          </div>
        )}
      </div>

      <div className="shrink-0 max-h-[55%] overflow-y-auto">
        <TerminalAccordionDock onJumpTo={onJumpToTerminal} />
      </div>
    </div>
  );
}

export default ContextStage;
