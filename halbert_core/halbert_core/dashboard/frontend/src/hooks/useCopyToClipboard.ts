// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * useCopyToClipboard - Hook for clipboard operations with feedback
 * 
 * Phase 20D: Extracted from repeated pattern across pages
 * 
 * Features:
 * - Copy text to clipboard
 * - Track which item was copied (by ID)
 * - Auto-clear copied state after timeout
 */

import { useState, useCallback } from 'react'

interface UseCopyToClipboardOptions {
  /** Timeout in ms before clearing copied state (default: 2000) */
  timeout?: number
}

interface UseCopyToClipboardReturn {
  /** ID of the currently copied item (null if none) */
  copiedId: string | null
  /** Copy text to clipboard and set copiedId */
  copy: (text: string, id: string) => void
  /** Check if a specific ID was just copied */
  isCopied: (id: string) => boolean
}

/**
 * Hook for copying text to clipboard with visual feedback
 * 
 * @example
 * ```tsx
 * const { copiedId, copy, isCopied } = useCopyToClipboard()
 * 
 * <button onClick={() => copy(path, item.id)}>
 *   {isCopied(item.id) ? <Check /> : <Copy />}
 * </button>
 * ```
 */
export function useCopyToClipboard({
  timeout = 2000,
}: UseCopyToClipboardOptions = {}): UseCopyToClipboardReturn {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copy = useCallback((text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), timeout)
  }, [timeout])

  const isCopied = useCallback((id: string) => {
    return copiedId === id
  }, [copiedId])

  return { copiedId, copy, isCopied }
}

export default useCopyToClipboard
