// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ShellModeContext — which of Halbert's two surfaces is on screen.
 *
 * Halbert is a dual-mode application (REVIEW-DESIGN-MECHANICS §2):
 *
 *   engaged  — the machine itself: a conversation spine you talk to it
 *              through, and a context stage holding its vitals and the
 *              terminal dock. The default, because it is what the product is.
 *              The mode switch labels this tab with the machine's own name.
 *   browsing  — the system administration hub. Every dashboard page, exactly
 *              as it has always been. Nothing was removed to make room for
 *              engaged mode; the two modes are one keystroke apart.
 *
 * The choice is per-machine (localStorage), so the app reopens where the user
 * left it.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

export type ShellMode = 'engaged' | 'browsing';

const STORAGE_KEY = 'halbert:shell-mode';

interface ShellModeValue {
  mode: ShellMode;
  setMode: (mode: ShellMode) => void;
  toggleMode: () => void;
  isEngaged: boolean;
}

const ShellModeContext = createContext<ShellModeValue | null>(null);

function readStoredMode(): ShellMode {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'engaged' || stored === 'browsing') return stored;
  } catch {
    // private mode / storage disabled — fall through to the default
  }
  return 'engaged';
}

export function ShellModeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ShellMode>(readStoredMode);

  const setMode = useCallback((next: ShellMode) => {
    setModeState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // non-fatal: the mode still applies for this session
    }
  }, []);

  const toggleMode = useCallback(() => {
    setModeState((prev) => {
      const next: ShellMode = prev === 'engaged' ? 'browsing' : 'engaged';
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // non-fatal
      }
      return next;
    });
  }, []);

  // Cmd+B (macOS) / Ctrl+B — flip between the two surfaces from anywhere.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        toggleMode();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [toggleMode]);

  const value = useMemo<ShellModeValue>(
    () => ({ mode, setMode, toggleMode, isEngaged: mode === 'engaged' }),
    [mode, setMode, toggleMode],
  );

  return <ShellModeContext.Provider value={value}>{children}</ShellModeContext.Provider>;
}

export function useShellMode(): ShellModeValue {
  const ctx = useContext(ShellModeContext);
  if (!ctx) {
    throw new Error('useShellMode must be used inside a ShellModeProvider');
  }
  return ctx;
}

export default ShellModeContext;
