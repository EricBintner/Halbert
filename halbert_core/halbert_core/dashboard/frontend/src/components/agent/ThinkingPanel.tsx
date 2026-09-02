// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ThinkingPanel Component
 * 
 * Displays the agent's thinking/reasoning process in real-time.
 * Supports collapsible sections and streaming updates.
 */

import { memo, useId, useMemo, useState, useRef, useEffect } from 'react';

interface ThinkingPanelProps {
  thinking: string;
  isStreaming?: boolean;
  maxHeight?: string;
  className?: string;
}

function ThinkingPanelImpl({ 
  thinking, 
  isStreaming = false,
  maxHeight = '200px',
  className = '' 
}: ThinkingPanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);
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

  // Reasoning streams in like the reply does, so this ran its four regexes
  // over the whole text on every animation frame (R11-12). Keyed on the
  // text: a frame that added nothing does no work.
  const sections = useMemo(() => parseThinkingSections(thinking), [thinking]);

  return (
    <div className={`border rounded-lg overflow-hidden ${className}`}>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        aria-expanded={isExpanded}
        aria-controls={bodyId}
        className="w-full px-4 py-2 flex items-center justify-between bg-muted hover:bg-muted transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground">
            {isStreaming ? 'Thinking...' : 'Thought Process'}
          </span>
          {isStreaming && (
            <span className="inline-flex items-center">
              <span className="animate-pulse text-info text-xs">●</span>
            </span>
          )}
        </div>
        <span className="text-muted-foreground text-sm">
          {isExpanded ? '▲' : '▼'}
        </span>
      </button>

      {isExpanded && (
        <div id={bodyId} className="border-t">
          {sections.length > 1 ? (
            <div className="divide-y">
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
              className="p-4 text-xs text-muted-foreground whitespace-pre-wrap overflow-auto bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
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
    <div>
      <button
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={Boolean(isOpen)}
        aria-controls={bodyId}
        className="w-full px-4 py-2 flex items-center justify-between hover:bg-muted text-left"
      >
        <span className="text-xs font-medium text-muted-foreground">{title}</span>
        <div className="flex items-center gap-2">
          {isStreaming && isLast && (
            <span className="animate-pulse text-info text-xs">●</span>
          )}
          <span className="text-muted-foreground text-xs">{isOpen ? '−' : '+'}</span>
        </div>
      </button>
      {isOpen && (
        <pre id={bodyId} className="px-4 pb-3 text-xs text-muted-foreground whitespace-pre-wrap">
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
