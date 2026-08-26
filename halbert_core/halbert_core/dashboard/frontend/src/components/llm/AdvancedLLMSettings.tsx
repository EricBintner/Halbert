// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { Toggle } from '@/components/prep-primitives/Toggle';
import type { AdvancedLLMSettings as AdvancedSettings } from '@/types/llm';

interface Props {
  value: AdvancedSettings;
  onChange: (next: AdvancedSettings) => void;
}

export function AdvancedLLMSettings({ value, onChange }: Props): JSX.Element {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-lg border border-border bg-surface">
      {/* Collapsible header */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-text hover:bg-surface-raised/50 transition-colors rounded-lg"
      >
        <span>Advanced LLM Settings</span>
        {open ? (
          <ChevronDown className="w-4 h-4 text-text-muted shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-text-muted shrink-0" />
        )}
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-5 border-t border-border/60">
          {/* 1. Enforce Cloud Token Safety Limits */}
          <div className="flex items-start justify-between gap-4 pt-4">
            <div className="flex-1 min-w-0">
              <label className="text-xs font-medium text-text">
                Enforce Cloud Token Safety Limits
              </label>
              <p className="text-[10px] text-text-muted mt-0.5 leading-relaxed">
                When ON, :cloud models use the conservative CLOUD_SMALL batch profile. Disable only
                on paid Ollama Cloud plans.
              </p>
            </div>
            <Toggle
              checked={value.enforce_cloud_token_safety}
              onChange={(checked) =>
                onChange({ ...value, enforce_cloud_token_safety: checked })
              }
              size="sm"
              className="shrink-0 mt-0.5"
            />
          </div>

          {/* 2. Max Thinking Budget */}
          <div className="space-y-1.5">
            <label className="block text-xs font-medium text-text">Max Thinking Budget</label>
            <input
              type="number"
              min={4096}
              max={131072}
              step={1024}
              value={value.max_thinking_budget}
              onChange={(e) =>
                onChange({
                  ...value,
                  max_thinking_budget: Math.max(
                    4096,
                    Math.min(131072, parseInt(e.target.value, 10) || 24576)
                  ),
                })
              }
              className="w-full bg-surface border border-border rounded px-2.5 py-1.5 text-xs text-text focus:outline-none focus:ring-1 focus:ring-primary"
            />
            <p className="text-[10px] text-text-muted leading-relaxed">
              Hard cap on <code className="font-mono">num_predict</code> when{' '}
              <code className="font-mono">think=True</code> (thinking-capable models). Default 24576.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
