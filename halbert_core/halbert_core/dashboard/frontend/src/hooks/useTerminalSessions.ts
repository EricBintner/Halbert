// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * useTerminalSessions — singleton store of live PTY sessions (E1a).
 *
 * One WebSocket per session (ws /ws/terminal/{id}), with a bounded scrollback
 * buffer and per-session status (running/done/idle). At most MAX_VISIBLE
 * sessions are flagged "visible" (driving live xterm.js instances); the rest
 * stay headless in the store so their output is preserved when re-attached.
 *
 * Sessions arrive two ways:
 *   - `spawn()` / `attach()` — a real PTY owned by the backend session manager.
 *     Transport 'ws': full duplex over /ws/terminal/{id}, stdin and resize work.
 *   - `adopt()` — a command the *agent* started mid-turn (E1f). Transport 'sse':
 *     output arrives as terminal_output events on the agent stream and is
 *     pushed in with `appendOutput`; there is no stdin to write to.
 *
 * Backend contract (B1e/B1f):
 *   POST   /api/terminal/sessions            -> {session_id, pid, sandboxed}
 *   DELETE /api/terminal/sessions/{id}        -> kill
 *   WS     /ws/terminal/{id}                  -> {type:'stdout',data} | {type:'exit',code}
 *   client -> {type:'stdin',data} | {type:'resize',cols,rows}
 */

import { useSyncExternalStore, useCallback } from 'react';
import { apiUrl, wsUrl as backendWsUrl } from '@/lib/apiBase';

export type TerminalSessionStatus = 'running' | 'done' | 'idle';

/**
 * A somatic block running inside a terminal session (Plan B). Long-running
 * blocks are promoted to task cards that appear in the Tasks column.
 */
export type TerminalBlockStatus = 'running' | 'needs_attention' | 'completed';

export interface TerminalBlock {
  block_id: string;
  owner: string;
  status: TerminalBlockStatus;
  /** True once promoted to a task card (terminal_block_promote / promote flag). */
  isTaskCard: boolean;
  label?: string;
}

/**
 * How a session's output reaches the store. 'ws' sessions are interactive PTYs;
 * 'sse' sessions are read-only mirrors of a command the agent is running.
 */
export type TerminalTransport = 'ws' | 'sse';

export interface TerminalSession {
  id: string;
  pid: number;
  command: string;
  status: TerminalSessionStatus;
  output: string; // bounded scrollback
  droppedChars: number; // monotonic count of chars trimmed from the front
  exitCode: number | null;
  visible: boolean;
  sandboxed: boolean;
  startedAt: number; // epoch ms when spawned (for the tile's elapsed timer)
  transport: TerminalTransport;
  cwd?: string;
  /** Agent turn that spawned this session, when it came from the agent stream. */
  originSessionId?: string;
  /** Somatic blocks owned by this session (Plan B). */
  blocks: TerminalBlock[];
  /** Block id this session was spawned to host, when known up front. */
  blockId?: string;
  /** Owner label for the block this session hosts. */
  owner?: string;
}

/** What the agent stream knows about a session it did not open locally. */
export interface AdoptInfo {
  command?: string;
  pid?: number;
  sandboxed?: boolean;
  cwd?: string;
  originSessionId?: string;
  blockId?: string;
  owner?: string;
}

export interface SpawnOptions {
  cwd?: string;
  cols?: number;
  rows?: number;
  writablePaths?: string[];
}

const MAX_VISIBLE = 3;
const SCROLLBACK_MAX_CHARS = 1_000_000; // ~1 MiB of chars

function wsUrl(id: string): string {
  return backendWsUrl(`/ws/terminal/${id}`);
}

class TerminalSessionStore {
  private sessions = new Map<string, TerminalSession>();
  private sockets = new Map<string, WebSocket>();
  private listeners = new Set<() => void>();
  private snapshot: TerminalSession[] = [];

  // ---------- external store contract ----------
  subscribe = (cb: () => void): (() => void) => {
    this.listeners.add(cb);
    return () => {
      this.listeners.delete(cb);
    };
  };

  getSnapshot = (): TerminalSession[] => this.snapshot;

  private emit(): void {
    this.snapshot = Array.from(this.sessions.values());
    this.listeners.forEach((l) => l());
  }

  // ---------- spawn ----------
  async spawn(command: string, opts: SpawnOptions = {}): Promise<string> {
    const body: Record<string, unknown> = {
      command,
      cols: opts.cols ?? 80,
      rows: opts.rows ?? 24,
    };
    if (opts.cwd) body.cwd = opts.cwd;
    if (opts.writablePaths) body.writable_paths = opts.writablePaths;

    const resp = await fetch(apiUrl('/api/terminal/sessions'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      throw new Error(`spawn failed: ${resp.status} ${await resp.text()}`);
    }
    const data = await resp.json();
    const id: string = data.session_id;
    const session: TerminalSession = {
      id,
      pid: data.pid,
      command,
      status: 'running',
      output: '',
      droppedChars: 0,
      exitCode: null,
      visible: this.visibleCount() < MAX_VISIBLE,
      sandboxed: !!data.sandboxed,
      startedAt: Date.now(),
      transport: 'ws',
      cwd: opts.cwd,
      blocks: [],
    };
    this.sessions.set(id, session);
    this.connect(id);
    this.emit();
    return id;
  }

  // ---------- sessions started elsewhere (E1f) ----------

  /**
   * Register a PTY the backend already spawned (e.g. the agent asked the
   * session manager for one) and attach a WebSocket to it. Idempotent: a
   * second call for the same id is ignored so a replayed SSE event cannot
   * open two sockets onto one PTY.
   */
  attach(id: string, info: AdoptInfo = {}): void {
    if (this.sessions.has(id)) return;
    this.sessions.set(id, this.makeSession(id, info, 'ws'));
    this.connect(id);
    this.emit();
  }

  /**
   * Register a command the agent is running whose output arrives on the agent
   * SSE stream rather than a socket. Read-only: no stdin, no resize.
   */
  adopt(id: string, info: AdoptInfo = {}): void {
    if (this.sessions.has(id)) return;
    this.sessions.set(id, this.makeSession(id, info, 'sse'));
    this.emit();
  }

  /** Append a chunk of output to an adopted session (terminal_output). */
  appendOutput(id: string, data: string): void {
    const s = this.sessions.get(id);
    if (!s || !data) return;
    s.output += data;
    if (s.output.length > SCROLLBACK_MAX_CHARS) {
      const dropped = s.output.length - SCROLLBACK_MAX_CHARS;
      s.output = s.output.slice(-SCROLLBACK_MAX_CHARS);
      s.droppedChars += dropped;
    }
    this.emit();
  }

  /** Mark a session finished (terminal_complete / ws exit). */
  complete(id: string, exitCode: number): void {
    const s = this.sessions.get(id);
    if (!s) return;
    s.status = 'done';
    s.exitCode = exitCode;
    this.emit();
  }

  // ---------- somatic blocks (Plan B) ----------

  /**
   * Push a block record into a session's block list (terminal_block). When
   * `promote` is true the block is born as a task card. Idempotent on block_id
   * so a replayed SSE event cannot duplicate a block.
   */
  addBlock(id: string, block: TerminalBlock): void {
    const s = this.sessions.get(id);
    if (!s) return;
    if (s.blocks.some((b) => b.block_id === block.block_id)) return;
    s.blocks.push(block);
    this.emit();
  }

  /** Promote a block to a task card (terminal_block_promote). */
  promoteBlock(id: string, blockId: string): void {
    const s = this.sessions.get(id);
    if (!s) return;
    const b = s.blocks.find((bl) => bl.block_id === blockId);
    if (b && !b.isTaskCard) {
      b.isTaskCard = true;
      this.emit();
    }
  }

  /** Mark a block as needing user input (terminal_needs_input). */
  setBlockNeedsAttention(id: string, blockId: string): void {
    const s = this.sessions.get(id);
    if (!s) return;
    const b = s.blocks.find((bl) => bl.block_id === blockId);
    if (b && b.status !== 'needs_attention') {
      b.status = 'needs_attention';
      this.emit();
    }
  }

  /** Mark a block's task completed (task_completed). */
  completeBlock(id: string, blockId: string): void {
    const s = this.sessions.get(id);
    if (!s) return;
    const b = s.blocks.find((bl) => bl.block_id === blockId);
    if (b && b.status !== 'completed') {
      b.status = 'completed';
      this.emit();
    }
  }

  private makeSession(
    id: string,
    info: AdoptInfo,
    transport: TerminalTransport,
  ): TerminalSession {
    return {
      id,
      pid: info.pid ?? 0,
      command: info.command ?? '',
      status: 'running',
      output: '',
      droppedChars: 0,
      exitCode: null,
      visible: this.visibleCount() < MAX_VISIBLE,
      sandboxed: !!info.sandboxed,
      startedAt: Date.now(),
      transport,
      cwd: info.cwd,
      originSessionId: info.originSessionId,
      blocks: [],
      blockId: info.blockId,
      owner: info.owner,
    };
  }

  private connect(id: string): void {
    const ws = new WebSocket(wsUrl(id));
    this.sockets.set(id, ws);

    ws.onmessage = (ev) => {
      let msg: { type?: string; data?: string; code?: number };
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      const s = this.sessions.get(id);
      if (!s) return;
      if (msg.type === 'stdout' && typeof msg.data === 'string') {
        s.output += msg.data;
        // bound the scrollback
        if (s.output.length > SCROLLBACK_MAX_CHARS) {
          const dropped = s.output.length - SCROLLBACK_MAX_CHARS;
          s.output = s.output.slice(-SCROLLBACK_MAX_CHARS);
          s.droppedChars += dropped;
        }
        this.emit();
      } else if (msg.type === 'exit') {
        s.status = 'done';
        s.exitCode = typeof msg.code === 'number' ? msg.code : -1;
        this.emit();
      }
    };

    ws.onclose = () => {
      const s = this.sessions.get(id);
      if (s && s.status === 'running') {
        // unexpected close before exit -> mark done
        s.status = 'done';
        s.exitCode = s.exitCode ?? -1;
        this.emit();
      }
      this.sockets.delete(id);
    };

    ws.onerror = () => {
      // best-effort; the close handler will tidy up
    };
  }

  // ---------- input / resize / kill ----------
  /** True when the session accepts keystrokes (a real PTY, still running). */
  isInteractive(id: string): boolean {
    const s = this.sessions.get(id);
    return !!s && s.transport === 'ws' && s.status === 'running';
  }

  sendInput(id: string, data: string): void {
    const ws = this.sockets.get(id);
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'stdin', data }));
    }
  }

  resize(id: string, cols: number, rows: number): void {
    const ws = this.sockets.get(id);
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'resize', cols, rows }));
    }
  }

  async kill(id: string): Promise<void> {
    const session = this.sessions.get(id);
    // Only PTY-backed sessions exist server-side; an SSE mirror has no
    // /api/terminal/sessions row and DELETEing it would just 404.
    if (!session || session.transport === 'ws') {
      try {
        await fetch(apiUrl(`/api/terminal/sessions/${id}`), { method: 'DELETE' });
      } catch {
        // ignore — close the socket regardless
      }
    }
    this.closeSocket(id);
    this.sessions.delete(id);
    this.emit();
  }

  /** Forget every session belonging to one agent turn (e.g. on reset). */
  clearOrigin(originSessionId: string): void {
    let changed = false;
    for (const [id, s] of Array.from(this.sessions.entries())) {
      if (s.originSessionId === originSessionId) {
        this.closeSocket(id);
        this.sessions.delete(id);
        changed = true;
      }
    }
    if (changed) this.emit();
  }

  private closeSocket(id: string): void {
    const ws = this.sockets.get(id);
    if (ws) {
      try {
        ws.close();
      } catch {
        // ignore
      }
      this.sockets.delete(id);
    }
  }

  // ---------- visibility (max 3 live xterm.js instances) ----------
  setVisible(id: string, visible: boolean): void {
    const s = this.sessions.get(id);
    if (!s) return;
    if (visible && !s.visible) {
      if (this.visibleCount() >= MAX_VISIBLE) {
        // demote the oldest currently-visible session
        const oldest = this.firstVisibleExcept(id);
        if (oldest) oldest.visible = false;
      }
      s.visible = true;
      this.emit();
    } else if (!visible && s.visible) {
      s.visible = false;
      this.emit();
    }
  }

  private visibleCount(): number {
    let n = 0;
    for (const s of this.sessions.values()) if (s.visible) n += 1;
    return n;
  }

  private firstVisibleExcept(id: string): TerminalSession | undefined {
    for (const s of this.sessions.values()) {
      if (s.visible && s.id !== id) return s;
    }
    return undefined;
  }

  // ---------- reads ----------
  get(id: string): TerminalSession | undefined {
    return this.sessions.get(id);
  }

  /** Close all sockets (e.g. on app teardown). */
  closeAll(): void {
    for (const id of Array.from(this.sockets.keys())) {
      this.closeSocket(id);
    }
    this.sessions.clear();
    this.emit();
  }
}

// Singleton store (module-level)
const store = new TerminalSessionStore();

export interface UseTerminalSessions {
  sessions: TerminalSession[];
  spawn: (command: string, opts?: SpawnOptions) => Promise<string>;
  sendInput: (id: string, data: string) => void;
  resize: (id: string, cols: number, rows: number) => void;
  kill: (id: string) => Promise<void>;
  setVisible: (id: string, visible: boolean) => void;
  isInteractive: (id: string) => boolean;
}

/**
 * React hook over the singleton terminal-session store. Components share one
 * store; each render subscribes via useSyncExternalStore.
 */
export function useTerminalSessions(): UseTerminalSessions {
  const sessions = useSyncExternalStore(store.subscribe, store.getSnapshot);

  const spawn = useCallback((command: string, opts?: SpawnOptions) => store.spawn(command, opts), []);
  const sendInput = useCallback((id: string, data: string) => store.sendInput(id, data), []);
  const resize = useCallback((id: string, cols: number, rows: number) => store.resize(id, cols, rows), []);
  const kill = useCallback((id: string) => store.kill(id), []);
  const setVisible = useCallback((id: string, visible: boolean) => store.setVisible(id, visible), []);
  const isInteractive = useCallback((id: string) => store.isInteractive(id), []);

  return { sessions, spawn, sendInput, resize, kill, setVisible, isInteractive };
}

export { store as terminalSessionStore };
