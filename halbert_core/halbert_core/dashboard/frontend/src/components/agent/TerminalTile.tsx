/**
 * TerminalTile — inline xterm.js terminal for a live PTY session (E1b).
 *
 * Renders one PTY session inline in the conversation stream: an xterm.js
 * terminal bound to the session's output (incremental writes), with a header
 * showing status badge / command / PID / elapsed timer and quick actions
 * (Pin/toggle-visible, Terminate, Copy). User input is forwarded to the
 * backend PTY via useTerminalSessions.sendInput; resize via FitAddon +
 * ResizeObserver calls store.resize.
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
  running: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  done: 'bg-slate-500/20 text-slate-300 border-slate-500/40',
  idle: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
};

function formatElapsed(startedAt: number, now: number): string {
  const s = Math.max(0, Math.floor((now - startedAt) / 1000));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, '0')}`;
}

export function TerminalTile({ session, onTerminated }: TerminalTileProps) {
  const { sendInput, resize, kill, setVisible } = useTerminalSessions();
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<XTerm | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const writtenRef = useRef(0); // chars already written to xterm
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
      cursorBlink: session.status === 'running',
      cursorStyle: 'bar',
      fontSize: 13,
      fontFamily: 'JetBrains Mono, Menlo, Monaco, monospace',
      scrollback: 5000,
      convertEol: true,
      theme: {
        background: '#1a1b26',
        foreground: '#a9b1d6',
        cursor: '#c0caf5',
        selectionBackground: '#33467c',
      },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.loadAddon(new WebLinksAddon());
    term.open(containerRef.current);
    fit.fit();
    termRef.current = term;
    fitRef.current = fit;

    // Forward keystrokes to the PTY
    const disposeData = term.onData((data) => sendInput(session.id, data));

    // Resize observer -> backend resize
    const ro = new ResizeObserver(() => {
      try {
        fit.fit();
        if (term.cols && term.rows) {
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

  // Write any new output incrementally (don't rewrite the whole buffer)
  useEffect(() => {
    const term = termRef.current;
    if (!term) return;
    const total = session.output.length;
    if (total > writtenRef.current) {
      term.write(session.output.slice(writtenRef.current));
      writtenRef.current = total;
    } else if (total < writtenRef.current) {
      // scrollback was trimmed in the store -> reset and rewrite
      term.reset();
      term.write(session.output);
      writtenRef.current = total;
    }
  }, [session.output]);

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
    <div className="my-2 rounded-lg border border-slate-700/60 bg-[#1a1b26] overflow-hidden shadow-lg">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-900/80 border-b border-slate-700/60 text-xs">
        <span className={`px-1.5 py-0.5 rounded border ${statusStyle} font-medium`}>
          {session.status === 'running' ? '● running' : session.status === 'done' ? `■ exit ${session.exitCode ?? '?'}` : '○ idle'}
        </span>
        <span className="text-slate-400 font-mono truncate flex-1" title={session.command}>
          $ {session.command}
        </span>
        <span className="text-slate-500 font-mono">pid {session.pid}</span>
        {session.status === 'running' && (
          <span className="text-slate-500 font-mono tabular-nums">{formatElapsed(session.startedAt, now)}</span>
        )}
        {session.sandboxed && (
          <span className="px-1 py-0.5 rounded bg-sky-500/20 text-sky-300 border border-sky-500/40">sandbox</span>
        )}

        {/* Quick actions */}
        <div className="flex items-center gap-1 ml-1">
          <button
            onClick={handlePin}
            title={session.visible ? 'Unpin (headless)' : 'Pin (live)'}
            className={`px-1.5 py-0.5 rounded ${session.visible ? 'bg-amber-500/20 text-amber-300' : 'bg-slate-700/50 text-slate-400 hover:text-slate-200'}`}
          >
            {session.visible ? '📌' : '📍'}
          </button>
          <button
            onClick={handleCopy}
            title="Copy output"
            className="px-1.5 py-0.5 rounded bg-slate-700/50 text-slate-400 hover:text-slate-200"
          >
            {copied ? '✓' : '⧉'}
          </button>
          {session.status === 'running' && (
            <button
              onClick={handleTerminate}
              title="Terminate"
              className="px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 hover:bg-rose-500/30 border border-rose-500/40"
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