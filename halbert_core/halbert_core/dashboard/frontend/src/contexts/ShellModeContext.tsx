// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ShellModeContext — which panels are on screen.
 *
 * The shell has three panels (left rail, center page, right conversation)
 * and a full-bleed voice route. The panel visibility model:
 *
 *   'both'     — center + right both visible (side-by-side co-pilot). Default.
 *   'engaged'  — right only (conversation focus). Center is hidden.
 *   'browsing' — center only (dashboard focus). Right is hidden.
 *   'voice'    — the /voice route: full-bleed, all panels hidden.
 *
 * Cmd+B flips between 'engaged' and 'browsing' (the two focus states).
 * Cmd+D toggles the center panel. Cmd+J toggles the right panel.
 *
 * The base choice is per-machine (localStorage), so the app reopens where the
 * user left it. Voice is never persisted: a reload lands on the route that
 * opened it, and the stored mode stays the surface the app reopens into.
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

export type ShellMode = 'engaged' | 'browsing' | 'both' | 'voice';

const STORAGE_KEY = 'halbert:shell-mode';

interface ShellModeValue {
  mode: ShellMode;
  setMode: (mode: ShellMode) => void;
  toggleMode: () => void;
  /** Park the current surface and take the shell for voice. */
  enterVoice: () => void;
  /** Give the shell back to the surface voice was entered from. */
  exitVoice: () => void;
  /** Toggle the center (dashboard/page) panel. */
  toggleCenter: () => void;
  /** Toggle the right (conversation) panel. */
  toggleRight: () => void;
  isEngaged: boolean;
  isVoice: boolean;
  /** Center panel is visible (not hidden). */
  centerVisible: boolean;
  /** Right panel (conversation) is visible. */
  rightVisible: boolean;
}

const ShellModeContext = createContext<ShellModeValue | null>(null);

/** Modes that represent panel visibility states (not voice). */
type PanelMode = 'engaged' | 'browsing' | 'both';

function readStoredMode(): ShellMode {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'engaged' || stored === 'browsing' || stored === 'both') return stored;
  } catch {
    // private mode / storage disabled — fall through to the default
  }
  return 'both';
}

/** Map a mode to which panels are visible. */
function centerVisibleFor(mode: ShellMode): boolean {
  return mode === 'browsing' || mode === 'both';
}
function rightVisibleFor(mode: ShellMode): boolean {
  return mode === 'engaged' || mode === 'both';
}

export function ShellModeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ShellMode>(readStoredMode);
  // The surface to hand the shell back to when voice ends. Voice is a parked
  // state, so this only ever holds a base mode.
  const restoreModeRef = useRef<PanelMode>('both');

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
      if (prev === 'voice') return prev;
      // Flip between the two focus states: engaged (right only) <-> browsing (center only)
      const next: PanelMode = prev === 'engaged' ? 'browsing' : 'engaged';
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // non-fatal
      }
      return next;
    });
  }, []);

  const toggleCenter = useCallback(() => {
    setModeState((prev) => {
      if (prev === 'voice') return prev;
      const cv = centerVisibleFor(prev);
      const rv = rightVisibleFor(prev);
      // If center is visible, hide it → right-only (engaged). If right is
      // also hidden, show right anyway — never leave both panels hidden.
      // If center is hidden, show it → both (if right is visible) or
      // browsing (center-only).
      const next: PanelMode = cv ? 'engaged' : (rv ? 'both' : 'browsing');
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // non-fatal
      }
      return next;
    });
  }, []);

  const toggleRight = useCallback(() => {
    setModeState((prev) => {
      if (prev === 'voice') return prev;
      const cv = centerVisibleFor(prev);
      const rv = rightVisibleFor(prev);
      // If right is visible, hide it → center-only (browsing). If center
      // is also hidden, show center anyway — never leave both hidden.
      // If right is hidden, show it → both (if center is visible) or
      // engaged (right-only).
      const next: PanelMode = rv ? 'browsing' : (cv ? 'both' : 'engaged');
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // non-fatal
      }
      return next;
    });
  }, []);

  // Cmd+B — flip between the two focus states (engaged <-> browsing).
  // Cmd+D — toggle center panel.
  // Cmd+J — toggle right panel.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.altKey || e.shiftKey) return;
      const key = e.key.toLowerCase()
      if (key === 'b') {
        e.preventDefault();
        toggleMode();
      } else if (key === 'd') {
        e.preventDefault();
        toggleCenter();
      } else if (key === 'j') {
        e.preventDefault();
        toggleRight();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [toggleMode, toggleCenter, toggleRight]);

  const centerVisible = centerVisibleFor(mode)
  const rightVisible = rightVisibleFor(mode)

  const value = useMemo<ShellModeValue>(
    () => ({
      mode,
      setMode,
      toggleMode,
      enterVoice,
      exitVoice,
      toggleCenter,
      toggleRight,
      isEngaged: mode === 'engaged',
      isVoice: mode === 'voice',
      centerVisible,
      rightVisible,
    }),
    [mode, setMode, toggleMode, enterVoice, exitVoice, toggleCenter, toggleRight, centerVisible, rightVisible],
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
