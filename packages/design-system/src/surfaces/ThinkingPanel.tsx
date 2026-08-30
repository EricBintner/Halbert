// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ThinkingPanel — collapsible agent reasoning viewer with streaming support.
 * Parses markdown-style section headers into nested accordions.
 */

import { useState, useRef, useEffect } from 'react'
import { cx } from '../lib'

export interface ThinkingPanelProps {
  thinking: string
  isStreaming?: boolean
  maxHeight?: string
  className?: string
}

export function ThinkingPanel({
  thinking,
  isStreaming = false,
  maxHeight = '200px',
  className,
}: ThinkingPanelProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const contentRef = useRef<HTMLPreElement>(null)

  useEffect(() => {
    if (contentRef.current && isStreaming) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight
    }
  }, [thinking, isStreaming])

  if (!thinking) return null

  const sections = parseThinkingSections(thinking)

  return (
    <div className={cx('hb-thinking', className)}>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="hb-thinking__toggle"
      >
        <span className="hb-thinking__toggle-left">
          <span>{isStreaming ? '🧠' : '💭'}</span>
          <span className="hb-thinking__toggle-label">
            {isStreaming ? 'Thinking...' : 'Thought Process'}
          </span>
          {isStreaming && <span className="hb-thinking__pulse">●</span>}
        </span>
        <span className="hb-thinking__arrow">{isExpanded ? '▲' : '▼'}</span>
      </button>

      {isExpanded && (
        <div className="hb-thinking__content">
          {sections.length > 1 ? (
            <div className="hb-thinking__sections">
              {sections.map((section, idx) => (
                <ThinkingSection
                  key={idx}
                  title={section.title}
                  content={section.content}
                  isLast={idx === sections.length - 1}
                  isStreaming={isStreaming && idx === sections.length - 1}
                />
              ))}
            </div>
          ) : (
            <pre ref={contentRef} className="hb-thinking__pre" style={{ maxHeight }}>
              {thinking}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}

interface ThinkingSectionProps {
  title: string
  content: string
  isLast?: boolean
  isStreaming?: boolean
}

function ThinkingSection({ title, content, isLast, isStreaming }: ThinkingSectionProps) {
  const [isOpen, setIsOpen] = useState(isLast)

  return (
    <div className="hb-thinking__section">
      <button onClick={() => setIsOpen(!isOpen)} className="hb-thinking__section-toggle">
        <span className="hb-thinking__section-title">{title}</span>
        <span className="hb-thinking__section-right">
          {isStreaming && isLast && <span className="hb-thinking__pulse">●</span>}
          <span>{isOpen ? '−' : '+'}</span>
        </span>
      </button>
      {isOpen && (
        <pre className="hb-thinking__section-pre">{content}</pre>
      )}
    </div>
  )
}

interface ParsedSection { title: string; content: string }

function parseThinkingSections(thinking: string): ParsedSection[] {
  const markers = [
    { pattern: /^## (.+)$/gm },
    { pattern: /^### (.+)$/gm },
    { pattern: /^(?:Step \d+|Phase \d+|Part \d+)[:.]?\s*(.+)$/gim },
    { pattern: /^(?:Analysis|Plan|Reasoning|Observation|Conclusion)[:.]?\s*$/gim },
  ]

  const sections: ParsedSection[] = []
  let currentTitle = 'Initial Thoughts'
  let currentContent: string[] = []

  for (const line of thinking.split('\n')) {
    let isHeader = false
    for (const marker of markers) {
      const match = line.match(marker.pattern)
      if (match) {
        if (currentContent.length > 0) {
          sections.push({ title: currentTitle, content: currentContent.join('\n').trim() })
        }
        currentTitle = match[1] || line.replace(/^#+\s*/, '')
        currentContent = []
        isHeader = true
        break
      }
    }
    if (!isHeader) currentContent.push(line)
  }

  if (currentContent.length > 0) {
    sections.push({ title: currentTitle, content: currentContent.join('\n').trim() })
  }

  return sections.length === 0 ? [{ title: 'Thinking', content: thinking }] : sections
}
