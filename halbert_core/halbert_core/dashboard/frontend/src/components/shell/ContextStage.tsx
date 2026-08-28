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
 *
 * Plan B (B19): below the md breakpoint, renders as a Sheet (bottom sheet)
 * opened from the aggregate StatusLight on the ModeSwitch tab. "Go back to
 * this" opens the sheet, scrolls the timeline, expands the task card.
 */

import { useState, type ReactNode } from 'react';
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
  /** Plan B: aggregate status light for the Sheet toggle (below md). */
  aggregateStatusLight?: ReactNode;
}

export function ContextStage({
  modules = [],
  onJumpToTerminal,
  className = '',
  aggregateStatusLight,
}: ContextStageProps) {
  const [sheetOpen, setSheetOpen] = useState(false);

  const stageContent: ReactNode = (
    <>
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
    </>
  );

  return (
    <>
      {/* Desktop (md+): full sidebar */}
      <div className={`hidden md:flex flex-col h-full min-h-0 bg-background ${className}`} data-context-stage="desktop">
        {stageContent}
      </div>

      {/* Mobile (<md): Sheet toggle + bottom sheet */}
      <div className="md:hidden" data-context-stage="mobile">
        {/* Toggle button with aggregate StatusLight */}
        <button
          onClick={() => setSheetOpen(true)}
          className="fixed bottom-4 right-4 z-40 flex items-center gap-2 rounded-full bg-surface border border-hairline shadow-lg px-3 py-2"
          aria-label="Open context panel"
          data-sheet-toggle
        >
          {aggregateStatusLight}
          <span className="text-xs text-text">Context</span>
        </button>

        {/* Bottom sheet */}
        {sheetOpen && (
          <>
            {/* Backdrop */}
            <div
              className="fixed inset-0 z-40 bg-black/40"
              onClick={() => setSheetOpen(false)}
              data-sheet-backdrop
            />
            {/* Sheet */}
            <div
              className="fixed bottom-0 left-0 right-0 z-50 max-h-[80vh] bg-background rounded-t-xl border-t border-hairline shadow-2xl flex flex-col"
              data-sheet
              role="dialog"
              aria-label="Context panel"
            >
              {/* Drag handle */}
              <div className="flex justify-center pt-2 pb-1 shrink-0">
                <div className="w-10 h-1 rounded-full bg-hairline" />
              </div>
              {/* Close button */}
              <button
                onClick={() => setSheetOpen(false)}
                className="absolute top-2 right-3 text-muted-foreground hover:text-text text-sm"
                aria-label="Close context panel"
              >
                ✕
              </button>
              {/* Content */}
              <div className="flex-1 min-h-0 overflow-y-auto">
                {stageContent}
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}

export default ContextStage;
