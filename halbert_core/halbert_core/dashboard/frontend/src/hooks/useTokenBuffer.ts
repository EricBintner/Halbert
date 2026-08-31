// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * useTokenBuffer — streaming text without a re-render per token.
 *
 * LLMs emit 30-80 tokens a second; the screen paints at ~60 Hz. Writing each
 * incoming chunk straight to React state costs one re-render and one
 * growing-string concatenation per token — O(n²) across a reply, and the
 * tree below re-parses the whole text on every one of those renders. Chunks
 * park in a ref instead and commit at most once per animation frame, which
 * caps the whole pipeline at the frame rate regardless of generation speed.
 *
 * The contract the consumer must keep, pinned by useTokenBuffer.test.ts:
 *  - `push` never commits; it schedules one frame per batch of chunks.
 *  - `flush` commits immediately and cancels the pending frame, so a stream
 *    that ends between frames loses nothing.
 *  - `set` REPLACES the committed text and drops the buffered tail (and its
 *    frame), so a final committed answer never has stream draft prepended.
 *  - `clear` drops both, so one turn's leftover draft cannot leak into the
 *    next turn's text.
 *  - a frame scheduled before unmount is cancelled, so no state update lands
 *    on a component that is gone.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

export interface UseTokenBufferReturn {
  /** Committed text: everything flushed so far, not the buffered tail. */
  value: string;
  /** Buffer a streaming chunk and schedule one rAF flush. */
  push: (chunk: string) => void;
  /** Commit the buffer now, cancelling any pending frame. */
  flush: () => void;
  /** Replace the committed text, dropping anything still buffered. */
  set: (next: string) => void;
  /** Drop both the committed text and the buffered tail. */
  clear: () => void;
}

export function useTokenBuffer(): UseTokenBufferReturn {
  const [value, setValue] = useState('');
  const bufferRef = useRef('');
  const rafRef = useRef<number | null>(null);

  const cancelFrame = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  const flush = useCallback(() => {
    cancelFrame();
    if (bufferRef.current !== '') {
      const chunk = bufferRef.current;
      bufferRef.current = '';
      setValue(v => v + chunk);
    }
  }, [cancelFrame]);

  const push = useCallback((chunk: string) => {
    if (chunk === '') return;
    bufferRef.current += chunk;
    // At most one frame in flight: the flush IS the render, so a second
    // scheduled frame would mean a second render for the same paint.
    if (rafRef.current === null) {
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = null;
        if (bufferRef.current === '') return;
        const pending = bufferRef.current;
        bufferRef.current = '';
        setValue(v => v + pending);
      });
    }
  }, []);

  const set = useCallback((next: string) => {
    // The buffered draft belongs to the text it was replacing; dropping it
    // (and its frame) is what keeps a committed answer free of stream
    // leftovers.
    cancelFrame();
    bufferRef.current = '';
    setValue(next);
  }, [cancelFrame]);

  const clear = useCallback(() => {
    set('');
  }, [set]);

  // Unmount or teardown: a frame still in flight must not fire afterwards.
  useEffect(() => cancelFrame, [cancelFrame]);

  return { value, push, flush, set, clear };
}

export default useTokenBuffer;