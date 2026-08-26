// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * MarkdownRenderer - Simple markdown renderer for LLM output
 * 
 * Phase 20D: Consolidated from Services.tsx and Network.tsx
 * 
 * Handles:
 * - # and ## headers
 * - **bold** text
 * - [links](url)
 * - Bullet points (-, *, •)
 * - Code blocks (```lang ... ```)
 * - Paragraphs
 */

import React from 'react'
import { CodeBlock } from './CodeBlock'

interface MarkdownRendererProps {
  /** Markdown text to render */
  text: string
  /** Callback for running code blocks */
  onRunCommand?: (command: string) => Promise<{ output?: string; error?: string; exit_code?: number }>
  /** Auto-analyze callback after command execution */
  onAutoAnalyze?: (command: string, output: string, isError: boolean) => void
  /** Compact mode - tighter spacing */
  compact?: boolean
}

/**
 * Format inline markdown: **bold**, [links](url)
 */
function formatInlineMarkdown(text: string): React.ReactNode {
  const parts: React.ReactNode[] = []
  let keyIndex = 0
  
  // Combined regex for **bold** and [link](url)
  const combinedRegex = /\*\*(.+?)\*\*|\[([^\]]+)\]\(([^)]+)\)/g
  let lastIndex = 0
  let match
  
  while ((match = combinedRegex.exec(text)) !== null) {
    // Add text before the match
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index))
    }
    
    if (match[1]) {
      // Bold text
      parts.push(<strong key={keyIndex++} className="font-semibold">{match[1]}</strong>)
    } else if (match[2] && match[3]) {
      // Link [text](url)
      parts.push(
        <a 
          key={keyIndex++} 
          href={match[3]} 
          target="_blank" 
          rel="noopener noreferrer"
          className="text-primary hover:underline"
        >
          {match[2]}
        </a>
      )
    }
    
    lastIndex = match.index + match[0].length
  }
  
  // Add remaining text
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }
  
  return parts.length > 0 ? parts : text
}

export function MarkdownRenderer({ 
  text, 
  onRunCommand,
  onAutoAnalyze,
  compact = false,
}: MarkdownRendererProps): React.ReactNode {
  if (!text) return null
  
  // DEBUG: Log the raw text to see if newlines are present
  console.log('[MarkdownRenderer] Input text (first 500 chars):', JSON.stringify(text.slice(0, 500)));
  console.log('[MarkdownRenderer] Has double newlines:', text.includes('\n\n'));
  console.log('[MarkdownRenderer] Newline count:', (text.match(/\n/g) || []).length);
  
  // First, extract and replace code blocks with placeholders
  const codeBlocks: Array<{ lang: string; code: string }> = []
  const textWithPlaceholders = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    codeBlocks.push({ lang: lang || 'bash', code: code.trim() })
    return `__CODE_BLOCK_${codeBlocks.length - 1}__`
  })
  
  // Normalize newlines: ensure headers and lists get their own paragraphs
  // This handles cases where LLM only uses single newlines
  const normalized = textWithPlaceholders
    .replace(/\n(#{1,3}\s)/g, '\n\n$1')  // Add double newline before headers
    .replace(/\n(\d+\.\s)/g, '\n\n$1')   // Add double newline before numbered lists
    .replace(/\n([-*•]\s)/g, '\n\n$1')   // Add double newline before bullet lists
    .replace(/\n(```)/g, '\n\n$1')       // Add double newline before code blocks
  
  // Split into paragraphs
  const paragraphs = normalized.split(/\n\n+/)
  
  return paragraphs.map((paragraph, pIndex) => {
    const trimmed = paragraph.trim()
    
    // Check if this is a code block placeholder
    const codeMatch = trimmed.match(/^__CODE_BLOCK_(\d+)__$/)
    if (codeMatch) {
      const block = codeBlocks[parseInt(codeMatch[1])]
      return (
        <CodeBlock 
          key={pIndex} 
          code={block.code} 
          lang={block.lang}
          onRun={onRunCommand}
          onAutoAnalyze={onAutoAnalyze}
          compact={compact}
        />
      )
    }
    
    // Handle ## headers (section headers)
    if (trimmed.startsWith('## ')) {
      return (
        <h3 key={pIndex} className="font-semibold text-sm text-primary mt-4 mb-2 pb-1 border-b border-border first:mt-0">
          {trimmed.slice(3)}
        </h3>
      )
    }
    
    // Handle # headers (main title)
    if (trimmed.startsWith('# ')) {
      return (
        <h2 key={pIndex} className="font-bold text-base mt-3 mb-2 first:mt-0">
          {trimmed.slice(2)}
        </h2>
      )
    }
    
    // Handle numbered lists (lines starting with 1. 2. etc)
    if (trimmed.match(/^\d+\.\s/m)) {
      const items = trimmed.split(/\n/).filter(line => line.trim())
      return (
        <ol key={pIndex} className={`space-y-1.5 my-2 ml-1 list-decimal list-inside ${compact ? 'my-1' : ''}`}>
          {items.map((item, iIndex) => (
            <li key={iIndex} className="text-sm">
              <span>{formatInlineMarkdown(item.replace(/^\d+\.\s*/, ''))}</span>
            </li>
          ))}
        </ol>
      )
    }
    
    // Handle bullet points (lines starting with - or *)
    if (trimmed.match(/^[-*•]\s/m)) {
      const items = trimmed.split(/\n/).filter(line => line.trim())
      return (
        <ul key={pIndex} className={`space-y-1.5 my-2 ml-1 ${compact ? 'my-1' : ''}`}>
          {items.map((item, iIndex) => (
            <li key={iIndex} className="text-sm flex items-start gap-2">
              <span className="text-muted-foreground mt-1.5 text-[6px]">●</span>
              <span className="flex-1">{formatInlineMarkdown(item.replace(/^[-*•]\s*/, ''))}</span>
            </li>
          ))}
        </ul>
      )
    }
    
    // Regular paragraph with inline formatting
    return (
      <p key={pIndex} className={`text-sm leading-relaxed text-foreground/90 ${compact ? 'mb-2' : 'mb-3'} last:mb-0`}>
        {formatInlineMarkdown(trimmed)}
      </p>
    )
  })
}

export default MarkdownRenderer
