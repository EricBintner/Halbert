import React, { useState, useEffect, useRef } from 'react';
import { TerminalFrame } from './TerminalFrame';

export function AnimatedCLI({
  script,
  title,
  figure = 'FIG. 1',
  autoPlay = true,
  className = '',
}) {
  const [activeStepIndex, setActiveStepIndex] = useState(0);
  const [displayedUserInput, setDisplayedUserInput] = useState('');
  const [displayedAgentOutput, setDisplayedAgentOutput] = useState('');
  const [activeToolCall, setActiveToolCall] = useState(null);
  const [completedToolResults, setCompletedToolResults] = useState([]);
  const [isThinking, setIsThinking] = useState(false);
  const [isDone, setIsDone] = useState(false);

  const scriptRef = useRef(script);
  scriptRef.current = script;

  useEffect(() => {
    let isCancelled = false;

    async function runScript() {
      if (!autoPlay || !scriptRef.current) return;
      const events = scriptRef.current.events;

      // Reset state for loop
      setActiveStepIndex(0);
      setDisplayedUserInput('');
      setDisplayedAgentOutput('');
      setActiveToolCall(null);
      setCompletedToolResults([]);
      setIsThinking(false);
      setIsDone(false);

      const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

      for (let i = 0; i < events.length; i++) {
        if (isCancelled) return;
        const ev = events[i];
        setActiveStepIndex(i);

        if (ev.type === 'user_input') {
          const text = ev.text || '';
          const charDelay = ev.typingDelayMs || 30;
          for (let c = 0; c <= text.length; c++) {
            if (isCancelled) return;
            setDisplayedUserInput(text.slice(0, c));
            await delay(charDelay);
          }
          await delay(300);
        } else if (ev.type === 'agent_thinking') {
          setIsThinking(true);
          await delay(ev.durationMs || 600);
          setIsThinking(false);
        } else if (ev.type === 'tool_call') {
          setActiveToolCall({ tool: ev.tool, args: ev.args, statusText: ev.statusText });
          await delay(ev.durationMs || 700);
        } else if (ev.type === 'tool_result') {
          if (activeToolCall) {
            setCompletedToolResults((prev) => [
              ...prev,
              {
                tool: activeToolCall.tool,
                text: ev.text,
                status: ev.status || 'success',
              },
            ]);
          }
          setActiveToolCall(null);
        } else if (ev.type === 'pause') {
          await delay(ev.durationMs || 400);
        } else if (ev.type === 'agent_output') {
          const fullText = ev.text || '';
          const charDelay = ev.typewriterDelayMs || 14;
          for (let c = 0; c <= fullText.length; c++) {
            if (isCancelled) return;
            setDisplayedAgentOutput(fullText.slice(0, c));
            await delay(charDelay);
          }
        }
      }

      setIsDone(true);

      if (scriptRef.current.loop) {
        await delay(scriptRef.current.loopDelayMs || 5000);
        if (!isCancelled) {
          runScript();
        }
      }
    }

    runScript();

    return () => {
      isCancelled = true;
    };
  }, [script, autoPlay]);

  return (
    <TerminalFrame title={title || script?.title} figure={figure} className={className}>
      <div className="space-y-4">
        {/* User Prompt Line */}
        <div className="flex items-start space-x-2 text-[var(--color-ink)]">
          <span className="text-[var(--color-accent)] font-bold select-none">&gt;</span>
          <div className="flex-1 font-bold">
            {displayedUserInput}
            {!displayedAgentOutput && displayedUserInput.length < (script?.events[0]?.text?.length || 0) && (
              <span className="inline-block w-2.5 h-4.5 bg-[var(--color-ink)] ml-1 animate-pulse align-middle" />
            )}
          </div>
        </div>

        {/* Agent Thinking Indicator */}
        {isThinking && (
          <div className="flex items-center space-x-2 text-[var(--color-ink-secondary)] text-[12px] font-mono py-1 border-l-2 border-[var(--color-accent)] pl-2">
            <span className="w-2 h-2 bg-[var(--color-accent)] animate-ping" />
            <span className="uppercase tracking-wider">HALBERT INSPECTING HOST…</span>
          </div>
        )}

        {/* Completed Tool Calls */}
        {completedToolResults.map((res, idx) => (
          <div
            key={idx}
            className="flex items-center space-x-2 px-3 py-1.5 bg-[var(--color-surface-subtle)] border border-[var(--color-ink)] text-[12.5px]"
          >
            <span
              className={`w-2 h-2 ${
                res.status === 'warning' ? 'bg-[var(--color-status-warning)]' : 'bg-[var(--color-status-success)]'
              }`}
            />
            <span className="text-[var(--color-ink)] font-mono font-medium">{res.text}</span>
          </div>
        ))}

        {/* Active Tool Call in Progress */}
        {activeToolCall && (
          <div className="flex items-center space-x-2 px-3 py-1.5 bg-[var(--color-accent-tint)] border border-[var(--color-accent)] text-[12.5px] text-[var(--color-accent)] font-mono font-bold">
            <span className="w-2 h-2 bg-[var(--color-accent)] animate-pulse" />
            <span>{activeToolCall.statusText || `Calling ${activeToolCall.tool}…`}</span>
          </div>
        )}

        {/* Agent Typewriter Output */}
        {displayedAgentOutput && (
          <div className="pt-3 text-[var(--color-ink)] font-mono text-[13.5px] leading-relaxed whitespace-pre-line border-t-2 border-[var(--color-ink)]/15">
            {displayedAgentOutput}
            {!isDone && (
              <span className="inline-block w-2.5 h-4.5 bg-[var(--color-accent)] ml-1 animate-pulse align-middle" />
            )}
          </div>
        )}
      </div>
    </TerminalFrame>
  );
}
