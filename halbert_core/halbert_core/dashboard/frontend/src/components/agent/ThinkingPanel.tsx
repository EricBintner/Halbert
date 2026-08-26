// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ThinkingPanel Component
 * 
 * Displays the agent's thinking/reasoning process in real-time.
 * Supports collapsible sections and streaming updates.
 */

import { useState, useRef, useEffect } from 'react';

interface ThinkingPanelProps {
  thinking: string;
  isStreaming?: boolean;
  maxHeight?: string;
  className?: string;
}

export function ThinkingPanel({ 
  thinking, 
  isStreaming = false,
  maxHeight = '200px',
  className = '' 
}: ThinkingPanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const contentRef = useRef<HTMLPreElement>(null);

  // Auto-scroll when new content arrives
  useEffect(() => {
    if (contentRef.current && isStreaming) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [thinking, isStreaming]);

  if (!thinking) {
    return null;
  }

  // Parse thinking into sections if it has markers
  const sections = parseThinkingSections(thinking);

  return (
    <div className={`border rounded-lg overflow-hidden ${className}`}>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-2 flex items-center justify-between bg-muted hover:bg-muted transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">
            {isStreaming ? '🧠' : '💭'}
          </span>
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
        <div className="border-t">
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
              className="p-4 text-xs text-muted-foreground whitespace-pre-wrap overflow-auto bg-muted"
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

  return (
    <div>
      <button
        onClick={() => setIsOpen(!isOpen)}
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
        <pre className="px-4 pb-3 text-xs text-muted-foreground whitespace-pre-wrap">
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

export default ThinkingPanel;
