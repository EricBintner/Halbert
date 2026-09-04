// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ToolExecutionCard Component
 * 
 * Displays tool execution status with expandable details.
 * Based on research5.md Part 8.3.
 */

import { Fragment, useState, type ReactNode } from 'react';
import { type ToolExecution } from '../../hooks/useAgentStream';
import { useTerminalSessions } from '../../hooks/useTerminalSessions';
import { StatusLight, type StatusLightState } from './StatusLight';
import { TerminalTile } from './TerminalTile';

interface ToolExecutionCardProps {
  execution: ToolExecution;
  onRetry?: (executionId: string) => void;
  /** Plan B: block id for run_command blocks. */
  blockId?: string;
  /** Plan B: block output (frozen <pre> when block is complete). */
  blockOutput?: string;
  /** Plan B: block exit code. */
  blockExitCode?: number | null;
  /** Plan B: block duration in seconds. */
  blockDuration?: number;
  /** Plan B: frozen head of block output (first N lines). */
  outputHead?: string;
  /** Plan B: frozen tail of block output (last N lines). */
  outputTail?: string;
}

const STATUS_CONFIG = {
  running: {
    icon: '⟳',
    label: 'running',
    bgColor: 'bg-status-telemetry-bg',
    borderColor: 'border-status-telemetry-line',
    textColor: 'text-status-telemetry',
  },
  success: {
    icon: '✓',
    label: 'exit 0',
    bgColor: 'bg-status-nominal-bg',
    borderColor: 'border-status-nominal-line',
    textColor: 'text-status-nominal',
  },
  error: {
    icon: '✗',
    label: 'error',
    bgColor: 'bg-status-critical-bg',
    borderColor: 'border-status-critical-line',
    textColor: 'text-status-critical',
  },
};

export function ToolExecutionCard({
  execution,
  onRetry,
  blockId: blockIdProp,
  blockOutput: blockOutputProp,
  blockExitCode: blockExitCodeProp,
  blockDuration: blockDurationProp,
  outputHead: outputHeadProp,
  outputTail: outputTailProp,
}: ToolExecutionCardProps): ReactNode {
  const [isExpanded, setIsExpanded] = useState(false);
  const config = STATUS_CONFIG[execution.status];

  // The block id comes from the execution when no caller supplies one. Every
  // block branch below is gated on it, and for as long as the only source was
  // a prop, no caller passed one and none of them could render: the card fell
  // back to a generic box with the internal tool name on it. The prop stays
  // for the timeline, which reads blocks from storage rather than the stream.
  const blockId = blockIdProp ?? execution.blockId;
  // The block's result travels the same way: props first, then whatever the
  // stream stamped onto the execution. Without this the id was wired and the
  // data was not, so isShortBlock and suppressResult -- gated on a duration
  // and an output nobody supplied -- stayed false and the one-line result
  // remained unreachable.
  const blockExitCode = blockExitCodeProp ?? execution.blockExitCode;
  const blockDuration = blockDurationProp ?? execution.blockDuration;
  const outputHead = outputHeadProp ?? execution.blockOutputHead;
  const outputTail = outputTailProp ?? execution.blockOutputTail;
  // The whole-blob prop has no execution equivalent: head/tail is what the
  // host actually sends, and `frozenOutput` below prefers it anyway.
  const blockOutput =
    blockOutputProp ??
    (outputHead !== undefined || outputTail !== undefined
      ? `${outputHead ?? ''}${
          outputTail !== undefined && outputTail !== outputHead ? `\n${outputTail}` : ''
        }`
      : undefined);

  // Plan B: map execution status to StatusLight state
  const lightState: StatusLightState =
    execution.status === 'running' ? 'running' :
    execution.status === 'error' ? 'error' :
    'done_unseen';

  // Plan B: for run_command with a block, render the block output
  const isCommandBlock = execution.tool === 'run_command' && blockId;

  // Arguments as readable fields. A nested value still needs JSON to be
  // shown at all, but it is one value on one line rather than the whole
  // object pretty-printed across six.
  const argFields: Array<[string, string]> = Object.entries(execution.args ?? {}).map(
    ([key, value]) => [
      key,
      typeof value === 'string' ? value : JSON.stringify(value) ?? String(value),
    ],
  );

  // The command line, when this card is a shell command at all.
  const rawCommand = (execution.args as Record<string, unknown>)?.command;
  const commandLabel =
    execution.tool === 'run_command' && typeof rawCommand === 'string' && rawCommand
      ? rawCommand
      : undefined;
  // Suppress the card's own <pre> result when a block renders
  const suppressResult = isCommandBlock && blockOutput !== undefined;

  // Plan B: one-line result for short completed blocks
  const isShortBlock = isCommandBlock && blockDuration !== undefined && blockDuration < 2 && blockOutput !== undefined;

  // Plan B: live long-running blocks render a live xterm via TerminalTile.
  // Look up the terminal session hosting this block by blockId.
  const { sessions } = useTerminalSessions();
  const liveSession = isCommandBlock && execution.status === 'running'
    ? sessions.find((s) => s.blockId === blockId)
    : undefined;
  const isLiveBlock = !!liveSession;

  // Plan B: frozen block output — prefer output_head/tail over the whole blob.
  const hasHeadTail = outputHead !== undefined && outputTail !== undefined;
  // Head and tail are the SAME string for any short command: the host sends
  // head = first 20 lines and tail = the whole text when it fits in 4 KiB.
  // Joining them unconditionally printed the output twice with an elision
  // marker between, claiming a cut that never happened. The elision is only
  // honest when the two halves actually differ -- the same rule the backend
  // already applies in _format_block_result.
  const frozenOutput = hasHeadTail
    ? outputHead && outputTail && outputHead !== outputTail
      ? `${outputHead}\n\u2026\n${outputTail}`
      : outputHead || outputTail
    : blockOutput;

  return (
    <div
      className={`rounded-lg border ${config.borderColor} ${config.bgColor} overflow-hidden`}
      data-terminal-block={blockId}
    >
      {/* Header — StatusLight on a surface strip, not the status-tinted body.
          A <button> so keyboard users can expand/collapse with Enter/Space. */}
      <button
        type="button"
        className="flex items-center justify-between p-2 cursor-pointer hover:bg-opacity-80 bg-surface w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        onClick={() => setIsExpanded(!isExpanded)}
        aria-expanded={isExpanded}
        aria-controls={`tool-content-${execution.executionId}`}
      >
        <div className="flex items-center gap-2">
          <StatusLight
            state={lightState}
            exitCode={blockExitCode ?? (execution.status === 'error' ? 1 : 0)}
            size="sm"
          />
          <div className="min-w-0">
            {/* A shell command is named by what it ran, not by the Python
                function that ran it. `run_command` tells the reader nothing
                they did not already know; `smbstatus` is the thing they
                asked for. Non-command tools keep their name. */}
            <div className="font-medium text-foreground text-xs font-mono truncate">
              {commandLabel ?? execution.tool}
            </div>
            {/* Plan B: labels are measurements, not "Success"/"Error" */}
            <div className="text-[10px] text-muted-foreground">
              {isCommandBlock && blockExitCode != null
                ? `exit ${blockExitCode}${blockDuration != null ? ` · ${blockDuration.toFixed(1)}s` : ''}`
                : config.label}
            </div>
          </div>
        </div>
        <span className="text-muted-foreground text-xs" aria-hidden="true">
          {isExpanded ? '\u25B2' : '\u25BC'}
        </span>
      </button>

      {/* Plan B: short block one-line result (not expanded) */}
      {isShortBlock && !isExpanded && (
        <div className="px-2 pb-1 text-[10px] font-mono text-muted-foreground truncate">
          $ {String((execution.args as Record<string, unknown>)?.command ?? execution.tool)} · exit {blockExitCode ?? '?'}
        </div>
      )}

      {isExpanded && (
        <div
          id={`tool-content-${execution.executionId}`}
          role="region"
          aria-label={`${execution.tool} details`}
          className="border-t p-2 space-y-2"
        >
          {/* A shell command's arguments ARE the command, and the header
              already carries it; repeating it as {"command": "..."} adds
              braces, quotes and a second copy of the same fact. Every other
              tool shows its arguments as fields -- the path is the useful
              part, the JSON punctuation never was. */}
          {!commandLabel && argFields.length > 0 && (
            <div>
              <div className="text-[10px] font-medium text-muted-foreground mb-1">Arguments</div>
              <dl className="text-[10px] grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5">
                {argFields.map(([key, value]) => (
                  <Fragment key={key}>
                    <dt className="text-muted-foreground font-mono">{key}</dt>
                    <dd className="text-foreground font-mono break-all">{value}</dd>
                  </Fragment>
                ))}
              </dl>
            </div>
          )}

          {/* Plan B: live long-running block — render a live xterm via TerminalTile */}
          {isLiveBlock && liveSession && (
            <TerminalTile
              session={liveSession}
              blockId={blockId}
              owner="agent"
            />
          )}

          {/* Plan B: block output (frozen <pre>) — replaces the result <pre>.
              Uses output_head/tail when available instead of the whole blob. */}
          {isCommandBlock && !isLiveBlock && blockOutput !== undefined && (
            <div>
              <div className="text-[10px] font-medium text-muted-foreground mb-1">Block output</div>
              <pre className="text-[10px] bg-muted rounded p-1.5 overflow-x-auto border max-h-48">
                {frozenOutput}
              </pre>
            </div>
          )}

          {/* Suppress the raw result when a block renders */}
          {!suppressResult && execution.result !== undefined && (
            <div>
              <div className="text-[10px] font-medium text-muted-foreground mb-1">Result</div>
              <pre className="text-[10px] bg-muted rounded p-1.5 overflow-x-auto border max-h-24">
                {typeof execution.result === 'string'
                  ? execution.result
                  : JSON.stringify(execution.result, null, 2)}
              </pre>
            </div>
          )}

          {execution.error && (
            <div>
              <div className="text-[10px] font-medium text-destructive mb-1">Error</div>
              <pre className="text-[10px] bg-destructive/10 text-destructive rounded p-1.5 border border-destructive/30">
                {execution.error}
              </pre>
            </div>
          )}

          {execution.status === 'error' && onRetry && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onRetry(execution.executionId);
              }}
              className="text-xs text-primary hover:text-primary/80 font-medium"
            >
              Retry
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default ToolExecutionCard;
