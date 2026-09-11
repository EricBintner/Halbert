// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ThinkingPanel — borderless, collapsible reasoning disclosure.
 *
 * Header is "Thinking..." while streaming, transforms to
 * "Thought for {elapsed}" on the `thinking_complete` event.
 * Defaults to collapsed when finished; borderless, dim/italic,
 * minimal vertical space.
 *
 * Reference: warp/crates/warp_tui/src/agent_block_sections.rs:117-136
 * (finished_duration -> header swap, auto-collapse on finish).
 */

import { memo, useId, useMemo, useState, useRef, useEffect } from 'react';

interface ThinkingPanelProps {
  thinking: string;
  isStreaming?: boolean;
  /** Duration of the completed thinking phase, in ms. Null while streaming. */
  durationMs?: number | null;
  maxHeight?: string;
  className?: string;
}

function formatElapsed(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}m${secs}s`;
}

function ThinkingPanelImpl({
  thinking,
  isStreaming = false,
  durationMs = null,
  maxHeight = '200px',
  className = '',
}: ThinkingPanelProps) {
  const isFinished = !isStreaming && durationMs !== null;
  // Auto-collapse when thinking completes; expand while streaming.
  const [userToggled, setUserToggled] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  const contentRef = useRef<HTMLPreElement>(null);
  const bodyId = useId();

  // Auto-scroll when new content arrives
  useEffect(() => {
    if (contentRef.current && isStreaming) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [thinking, isStreaming]);

  if (!thinking) {
    return null;
  }

  // When the user has not overridden, default open while streaming,
  // collapsed when finished (warp reference pattern).
  const isOpen = userToggled ? userOpen : isStreaming;

  // Reasoning streams in like the reply does, so this ran its four regexes
  // over the whole text on every animation frame (R11-12). Keyed on the
  // text: a frame that added nothing does no work.
  const sections = useMemo(() => parseThinkingSections(thinking), [thinking]);

  const header = isFinished
    ? `Thought for ${formatElapsed(durationMs!)}`
    : 'Thinking...';

  return (
    <div className={`text-xs text-muted-foreground ${className}`}>
      <button
        onClick={() => { setUserToggled(true); setUserOpen(!isOpen); }}
        aria-expanded={isOpen}
        aria-controls={bodyId}
        className="w-full flex items-center gap-2 py-1 text-left text-muted-foreground italic hover:text-foreground transition-colors"
      >
        <span className="italic">{header}</span>
        {isStreaming && (
          <span className="animate-pulse text-info">●</span>
        )}
        <span className="text-hairline ml-auto">
          {isOpen ? '▾' : '▸'}
        </span>
      </button>

      {isOpen && (
        <div id={bodyId} className="mt-1">
          {sections.length > 1 ? (
            <div className="divide-y divide-hairline/40">
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
            <pre
              ref={contentRef}
              // A scrollable region has to be reachable and scrollable from
              // the keyboard alone (R11-09).
              tabIndex={0}
              role="region"
              aria-label="Thought process"
              className="py-2 text-xs text-muted-foreground italic whitespace-pre-wrap overflow-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
              style={{ maxHeight }}
            >
              {thinking}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

interface ThinkingSectionProps {
  title: string;
  content: string;
  isLast?: boolean;
  isStreaming?: boolean;
}

function ThinkingSection({ title, content, isLast, isStreaming }: ThinkingSectionProps) {
  const [isOpen, setIsOpen] = useState(isLast);
  const bodyId = useId();

  return (
    <div className="py-1">
      <button
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={Boolean(isOpen)}
        aria-controls={bodyId}
        className="w-full flex items-center justify-between text-left text-muted-foreground italic"
      >
        <span className="text-xs italic">{title}</span>
        <div className="flex items-center gap-2">
          {isStreaming && isLast && (
            <span className="animate-pulse text-info text-xs">●</span>
          )}
          <span className="text-hairline text-xs">{isOpen ? '▾' : '▸'}</span>
        </div>
      </button>
      {isOpen && (
        <pre id={bodyId} className="py-1 text-xs text-muted-foreground italic whitespace-pre-wrap">
          {content}
        </pre>
      )}
    </div>
  );
}

interface ParsedSection {
  title: string;
  content: string;
}

function parseThinkingSections(thinking: string): ParsedSection[] {
  // Common thinking section markers
  const markers = [
    { pattern: /^## (.+)$/gm, type: 'header' },
    { pattern: /^### (.+)$/gm, type: 'subheader' },
    { pattern: /^(?:Step \d+|Phase \d+|Part \d+)[:.]?\s*(.+)$/gim, type: 'step' },
    { pattern: /^(?:Analysis|Plan|Reasoning|Observation|Conclusion)[:.]?\s*$/gim, type: 'label' },
  ];

  const sections: ParsedSection[] = [];
  let currentTitle = 'Initial Thoughts';
  let currentContent: string[] = [];

  const lines = thinking.split('\n');

  for (const line of lines) {
    let isHeader = false;

    // Check for section markers
    for (const marker of markers) {
      const match = line.match(marker.pattern);
      if (match) {
        // Save previous section
        if (currentContent.length > 0) {
          sections.push({
            title: currentTitle,
            content: currentContent.join('\n').trim()
          });
        }

        currentTitle = match[1] || line.replace(/^#+\s*/, '');
        currentContent = [];
        isHeader = true;
        break;
      }
    }

    if (!isHeader) {
      currentContent.push(line);
    }
  }

  // Add final section
  if (currentContent.length > 0) {
    sections.push({
      title: currentTitle,
      content: currentContent.join('\n').trim()
    });
  }

  // If no sections found, return single section
  if (sections.length === 0) {
    return [{ title: 'Thinking', content: thinking }];
  }

  return sections;
}

export const ThinkingPanel = memo(ThinkingPanelImpl);

export default ThinkingPanel;
