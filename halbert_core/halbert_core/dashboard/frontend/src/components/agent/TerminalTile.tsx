// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * TerminalTile — inline xterm.js terminal for a live PTY session (E1b).
 *
 * Renders one PTY session inline in the conversation stream: an xterm.js
 * terminal bound to the session's output (incremental writes), with a header
 * showing status badge / command / PID / elapsed timer and quick actions
 * (Pin/toggle-visible, Terminate, Copy). User input is forwarded to the
 * backend PTY via useTerminalSessions.sendInput; resize via FitAddon +
 * ResizeObserver calls store.resize.
 *
 * Sessions the agent is mirroring over SSE (transport 'sse') are read-only:
 * there is no socket to write keystrokes to, so input, resize and terminate
 * are suppressed rather than silently dropped.
 */

import { useEffect, useRef, useState } from 'react';
import { Terminal as XTerm } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { WebLinksAddon } from '@xterm/addon-web-links';
import '@xterm/xterm/css/xterm.css';
import { useTerminalSessions, type TerminalSession } from '../../hooks/useTerminalSessions';

interface TerminalTileProps {
  session: TerminalSession;
  onTerminated?: (id: string) => void;
}

const STATUS_STYLES: Record<string, string> = {
  running: 'bg-success/20 text-success border-success/40',
  done: 'bg-muted/20 text-foreground border-border/40',
  idle: 'bg-warning/20 text-warning border-warning/40',
};

function formatElapsed(startedAt: number, now: number): string {
  const s = Math.max(0, Math.floor((now - startedAt) / 1000));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, '0')}`;
}

/**
 * Build xterm's theme from the live design tokens.
 *
 * xterm paints to a canvas and cannot read CSS variables, so the values have to
 * be resolved to concrete colours at mount time. Reading them from the document
 * rather than hardcoding a palette means the terminal follows the Olivetti
 * identity and the light/dark swap like everything else — the plan calls for a
 * bone-canvas terminal, not the Tokyo Night default this used to ship.
 */
function xtermTheme() {
  const root = typeof document !== 'undefined' ? document.documentElement : null;
  const read = (token: string, fallback: string) => {
    if (!root) return fallback;
    const value = getComputedStyle(root).getPropertyValue(token).trim();
    return value || fallback;
  };
  return {
    // The terminal interior is a recessed tray, not the page field.
    background: read('--color-surface-subtle', '#EDE8DC'),
    foreground: read('--color-ink', '#1C1917'),
    // The letterpress cursor.
    cursor: read('--color-accent-strong', '#C4451D'),
    selectionBackground: read('--color-accent-tint', '#FDF2EE'),
  };
}

export function TerminalTile({ session, onTerminated }: TerminalTileProps) {
  const { sendInput, resize, kill, setVisible } = useTerminalSessions();
  const interactive = session.transport === 'ws';
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<XTerm | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const writtenRef = useRef(0); // absolute stream chars already written to xterm
  const [now, setNow] = useState(Date.now());
  const [copied, setCopied] = useState(false);

  // 1s ticking clock for the elapsed timer (only while running)
  useEffect(() => {
    if (session.status !== 'running') return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [session.status]);

  // Mount the xterm instance once
  useEffect(() => {
    if (!containerRef.current || termRef.current) return;

    const term = new XTerm({
      cursorBlink: session.status === 'running' && interactive,
      disableStdin: !interactive,
      cursorStyle: 'bar',
      fontSize: 13,
      fontFamily: 'JetBrains Mono, Menlo, Monaco, monospace',
      scrollback: 5000,
      convertEol: true,
      theme: xtermTheme(),
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.loadAddon(new WebLinksAddon());
    term.open(containerRef.current);
    fit.fit();
    termRef.current = term;
    fitRef.current = fit;

    // Forward keystrokes to the PTY (only a real PTY can receive them)
    const disposeData = term.onData((data) => {
      if (interactive) sendInput(session.id, data);
    });

    // Resize observer -> backend resize
    const ro = new ResizeObserver(() => {
      try {
        fit.fit();
        if (interactive && term.cols && term.rows) {
          resize(session.id, term.cols, term.rows);
        }
      } catch {
        // ignore fit errors during teardown
      }
    });
    ro.observe(containerRef.current);

    return () => {
      disposeData.dispose();
      ro.disconnect();
      term.dispose();
      termRef.current = null;
      fitRef.current = null;
      writtenRef.current = 0;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.id]);

  // Write any new output incrementally (don't rewrite the whole buffer).
  // writtenRef is absolute (includes chars the store has dropped from the
  // front of the buffer), so trimming the scrollback does not stall the writer.
  useEffect(() => {
    const term = termRef.current;
    if (!term) return;
    const dropped = session.droppedChars;
    const absTotal = dropped + session.output.length;
    if (absTotal > writtenRef.current) {
      const start = writtenRef.current - dropped;
      if (start < 0) {
        // our write point fell out of the trimmed buffer -> resync on the tail
        term.reset();
        term.write(session.output);
      } else {
        term.write(session.output.slice(start));
      }
      writtenRef.current = absTotal;
    } else if (absTotal < writtenRef.current) {
      // buffer shrank behind us (store reset) -> reset and rewrite
      term.reset();
      term.write(session.output);
      writtenRef.current = absTotal;
    }
  }, [session.output, session.droppedChars]);

  const handleTerminate = async () => {
    await kill(session.id);
    onTerminated?.(session.id);
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(session.output);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      // clipboard may be unavailable
    }
  };

  const handlePin = () => setVisible(session.id, !session.visible);

  const statusStyle = STATUS_STYLES[session.status] ?? STATUS_STYLES.idle;

  return (
    <div className="my-2 rounded-lg border border-border/60 bg-[#1a1b26] overflow-hidden shadow-lg">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-1.5 bg-background/80 border-b border-border/60 text-xs">
        <span className={`px-1.5 py-0.5 rounded border ${statusStyle} font-medium`}>
          {session.status === 'running' ? '● running' : session.status === 'done' ? `■ exit ${session.exitCode ?? '?'}` : '○ idle'}
        </span>
        <span className="text-muted-foreground font-mono truncate flex-1" title={session.command}>
          $ {session.command}
        </span>
        <span className="text-muted-foreground font-mono">pid {session.pid}</span>
        {session.status === 'running' && (
          <span className="text-muted-foreground font-mono tabular-nums">{formatElapsed(session.startedAt, now)}</span>
        )}
        {session.sandboxed && (
          <span className="px-1 py-0.5 rounded bg-info/20 text-info border border-info/40">sandbox</span>
        )}
        {!interactive && (
          <span
            className="px-1 py-0.5 rounded bg-violet-500/20 text-violet-300 border border-violet-500/40"
            title="Halbert is running this — mirrored read-only"
          >
            agent
          </span>
        )}

        {/* Quick actions */}
        <div className="flex items-center gap-1 ml-1">
          <button
            onClick={handlePin}
            title={session.visible ? 'Unpin (headless)' : 'Pin (live)'}
            className={`px-1.5 py-0.5 rounded ${session.visible ? 'bg-warning/20 text-warning' : 'bg-muted/50 text-muted-foreground hover:text-foreground'}`}
          >
            {session.visible ? '📌' : '📍'}
          </button>
          <button
            onClick={handleCopy}
            title="Copy output"
            className="px-1.5 py-0.5 rounded bg-muted/50 text-muted-foreground hover:text-foreground"
          >
            {copied ? '✓' : '⧉'}
          </button>
          {session.status === 'running' && interactive && (
            <button
              onClick={handleTerminate}
              title="Terminate"
              className="px-1.5 py-0.5 rounded bg-error/20 text-error hover:bg-error/30 border border-error/40"
            >
              ⏹
            </button>
          )}
        </div>
      </div>

      {/* xterm container */}
      <div ref={containerRef} className="w-full h-48 px-1 py-1" />
    </div>
  );
}
