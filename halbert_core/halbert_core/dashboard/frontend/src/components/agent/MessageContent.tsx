// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * MessageContent — assistant text with fenced code blocks rendered as
 * runnable CodeBlocks. Shared by the live assistant block (AgentChat) and
 * the stored turns (Timeline) so a reply looks the same the moment it lands
 * and a week later.
 */

import { CodeBlock } from '../domain/CodeBlock';

export type RunCommand = (cmd: string) => Promise<{ output?: string; error?: string; exit_code?: number }>;

interface MessageContentProps {
  content: string;
  onRunCommand?: RunCommand;
}

export function MessageContent({ content, onRunCommand }: MessageContentProps) {
  const parts: Array<{ type: 'text' | 'code', content: string, lang?: string }> = [];
  const codeBlockRegex = /```(\w+)?\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;

  while ((match = codeBlockRegex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: 'text', content: content.slice(lastIndex, match.index) });
    }
    let codeContent = match[2].trim();
    codeContent = codeContent.replace(/^`+|`+$/g, '').trim();
    parts.push({ type: 'code', content: codeContent, lang: match[1] || 'bash' });
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < content.length) {
    parts.push({ type: 'text', content: content.slice(lastIndex) });
  }

  if (parts.length === 0) {
    parts.push({ type: 'text', content });
  }

  return (
    <div className="space-y-2 min-w-0 overflow-hidden">
      {parts.map((part, i) => {
        if (part.type === 'code') {
          return (
            <CodeBlock
              key={i}
              code={part.content}
              lang={part.lang || 'bash'}
              onRun={onRunCommand}
              compact
            />
          );
        }
        return (
          <span key={i} className="whitespace-pre-wrap break-words">{part.content}</span>
        );
      })}
    </div>
  );
}

export default MessageContent;
