/**
 * useTerminalSessions — singleton store of live PTY sessions (E1a).
 *
 * One WebSocket per session (ws /ws/terminal/{id}), with a bounded scrollback
 * buffer and per-session status (running/done/idle). At most MAX_VISIBLE
 * sessions are flagged "visible" (driving live xterm.js instances); the rest
 * stay headless in the store so their output is preserved when re-attached.
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
    };
    this.sessions.set(id, session);
    this.connect(id);
    this.emit();
    return id;
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
    try {
      await fetch(apiUrl(`/api/terminal/sessions/${id}`), { method: 'DELETE' });
    } catch {
      // ignore — close the socket regardless
    }
    this.closeSocket(id);
    this.sessions.delete(id);
    this.emit();
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

  return { sessions, spawn, sendInput, resize, kill, setVisible };
}

export { store as terminalSessionStore };