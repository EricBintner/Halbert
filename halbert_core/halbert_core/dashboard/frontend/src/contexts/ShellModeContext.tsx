// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ShellModeContext — which of Halbert's surfaces is on screen.
 *
 * Halbert's shell (REVIEW-DESIGN-MECHANICS §2, plan doc 16 O8):
 *
 *   engaged  — the machine itself: a conversation spine you talk to it
 *              through, and a context stage holding its vitals and the
 *              terminal dock. The default, because it is what the product is.
 *              The mode switch labels this tab with the machine's own name.
 *   browsing  — the system administration hub. Every dashboard page, exactly
 *              as it has always been. Nothing was removed to make room for
 *              engaged mode; the two modes are one keystroke apart.
 *   voice    — the /voice route: the machine spoken to, ear-first. It is a
 *              MODE, not a tab (like settings, like engaged) — no nav item,
 *              no switch tab. Entering it PARKS whatever surface was on and
 *              leaving it restores exactly that surface. It is never
 *              persisted: a reload lands on the route that opened it, and
 *              the stored mode stays the surface the app reopens into.
 *
 * The base choice is per-machine (localStorage), so the app reopens where the
 * user left it.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

export type ShellMode = 'engaged' | 'browsing' | 'voice';

const STORAGE_KEY = 'halbert:shell-mode';

interface ShellModeValue {
  mode: ShellMode;
  setMode: (mode: ShellMode) => void;
  toggleMode: () => void;
  /** Park the current surface and take the shell for voice (O8). */
  enterVoice: () => void;
  /** Give the shell back to the surface voice was entered from. */
  exitVoice: () => void;
  isEngaged: boolean;
  isVoice: boolean;
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
  // The surface to hand the shell back to when voice ends. Voice is a parked
  // state, so this only ever holds a base mode.
  const restoreModeRef = useRef<ShellMode>('engaged');

  const enterVoice = useCallback(() => {
    setModeState((prev) => {
      if (prev === 'voice') return prev;
      restoreModeRef.current = prev;
      return 'voice';
    });
  }, []);

  const exitVoice = useCallback(() => {
    setModeState((prev) => (prev === 'voice' ? restoreModeRef.current : prev));
  }, []);

  const setMode = useCallback(
    (next: ShellMode) => {
      // Entering voice through the generic setter is the same act as
      // enterVoice — the route effect and callers share one path.
      if (next === 'voice') {
        enterVoice();
        return;
      }
      setModeState(next);
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // non-fatal: the mode still applies for this session
      }
    },
    [enterVoice],
  );

  const toggleMode = useCallback(() => {
    setModeState((prev) => {
      // Voice is a route posture, not a tab: the mode switch is not on the
      // voice screen, so the shortcut has nothing to flip while it owns the
      // shell. The screen's own Host Canvas edge leaves voice.
      if (prev === 'voice') return prev;
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
    () => ({
      mode,
      setMode,
      toggleMode,
      enterVoice,
      exitVoice,
      isEngaged: mode === 'engaged',
      isVoice: mode === 'voice',
    }),
    [mode, setMode, toggleMode, enterVoice, exitVoice],
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
