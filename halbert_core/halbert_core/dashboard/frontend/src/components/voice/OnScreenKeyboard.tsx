// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
// On-screen keyboard for Voice Mode touch input (spec §6.2(2)).
//
// Bottom-sheet glide: the mark scales to a 48px header emblem (medium tier,
// deliberately NOT the reactive component). Keyboard input writes into the
// same sendMessage path as the chat input. Quick-intent chips provide
// one-tap shortcuts for common queries.

import { useState, useCallback } from 'react'
import { HalbertMark } from '@halbert/design-system'
import { Keyboard, X, Send, Delete, Mic } from 'lucide-react'

const QUICK_CHIPS = [
  'System Vitals',
  'Check Storage',
  'Lock Doors',
  'Run Health Scan',
] as const

const KEYBOARD_ROWS = [
  ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
  ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
  ['z', 'x', 'c', 'v', 'b', 'n', 'm', ',', '.', '?'],
] as const

interface OnScreenKeyboardProps {
  onSend: (message: string) => void
  onDismiss: () => void
  onMic?: () => void
}

export function OnScreenKeyboard({ onSend, onDismiss, onMic }: OnScreenKeyboardProps) {
  const [text, setText] = useState('')

  const appendKey = useCallback((key: string) => {
    setText((prev) => prev + key)
  }, [])

  const backspace = useCallback(() => {
    setText((prev) => prev.slice(0, -1))
  }, [])

  const send = useCallback(() => {
    const trimmed = text.trim()
    if (!trimmed) return
    onSend(trimmed)
    setText('')
  }, [text, onSend])

  const sendChip = useCallback((chip: string) => {
    onSend(chip)
  }, [onSend])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      send()
    }
  }, [send])

  return (
    <div
      className="fixed bottom-0 left-0 right-0 z-40 bg-black/95 border-t border-vermilion/20 rounded-t-2xl shadow-2xl"
      role="dialog"
      aria-label="On-screen keyboard"
    >
      {/* Header: mark emblem + title + dismiss + mic */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-3">
          <HalbertMark size={48} density="medium" tone="accent" />
          <div className="flex items-center gap-1.5 text-white/70">
            <Keyboard className="h-4 w-4" />
            <span className="text-sm font-medium">Keyboard Input</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {onMic && (
            <button
              onClick={onMic}
              className="flex h-10 w-10 items-center justify-center rounded-full bg-vermilion/20 text-vermilion transition-colors hover:bg-vermilion/30"
              aria-label="Switch to voice input"
            >
              <Mic className="h-5 w-5" />
            </button>
          )}
          <button
            onClick={onDismiss}
            className="flex h-10 w-10 items-center justify-center rounded-full bg-white/5 text-white/60 transition-colors hover:bg-white/10"
            aria-label="Dismiss keyboard"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      </div>

      {/* Text input preview + send */}
      <div className="flex items-center gap-2 px-4 py-3">
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message..."
          className="flex-1 rounded-lg bg-white/5 px-4 py-3 text-base text-white placeholder:text-white/30 outline-none focus:ring-1 focus:ring-vermilion/40"
          aria-label="Message text input"
          autoFocus
        />
        <button
          onClick={backspace}
          className="flex h-12 w-12 items-center justify-center rounded-lg bg-white/5 text-white/60 transition-colors hover:bg-white/10"
          aria-label="Backspace"
        >
          <Delete className="h-5 w-5" />
        </button>
        <button
          onClick={send}
          disabled={!text.trim()}
          className="flex h-12 w-12 items-center justify-center rounded-lg bg-vermilion text-white transition-colors hover:bg-vermilion-strong disabled:opacity-30"
          aria-label="Send message"
        >
          <Send className="h-5 w-5" />
        </button>
      </div>

      {/* Quick-intent chips */}
      <div className="flex flex-wrap gap-2 px-4 pb-3">
        {QUICK_CHIPS.map((chip) => (
          <button
            key={chip}
            onClick={() => sendChip(chip)}
            className="rounded-full border border-vermilion/30 bg-vermilion/10 px-4 py-2 text-sm text-vermilion transition-colors hover:bg-vermilion/20 active:bg-vermilion/30"
          >
            {chip}
          </button>
        ))}
      </div>

      {/* Keyboard rows */}
      <div className="space-y-1.5 px-4 pb-4">
        {KEYBOARD_ROWS.map((row, rowIdx) => (
          <div key={rowIdx} className="flex justify-center gap-1.5">
            {row.map((key) => (
              <button
                key={key}
                onClick={() => appendKey(key)}
                className="flex h-12 w-12 items-center justify-center rounded-lg bg-white/8 text-base text-white/90 transition-colors hover:bg-white/15 active:bg-vermilion/30"
                aria-label={`Key ${key}`}
              >
                {key}
              </button>
            ))}
          </div>
        ))}
        <div className="flex justify-center gap-1.5">
          <button
            onClick={() => appendKey(' ')}
            className="flex h-12 w-48 items-center justify-center rounded-lg bg-white/8 text-base text-white/90 transition-colors hover:bg-white/15 active:bg-vermilion/30"
            aria-label="Space"
          >
            space
          </button>
        </div>
      </div>
    </div>
  )
}
