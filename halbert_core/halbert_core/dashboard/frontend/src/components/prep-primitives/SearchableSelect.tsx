// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react';
import { ChevronDown, Search, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { SelectOption } from './Select';

export interface SearchableSelectProps {
  options: SelectOption[];
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  size?: 'default' | 'sm' | 'lg';
  searchThreshold?: number;
}

const sizeClass = {
  default: 'h-10 px-3 py-2 text-sm',
  sm:      'h-9 px-2 py-1 text-xs',
  lg:      'h-11 px-4 py-2 text-sm',
};

export function SearchableSelect({
  options,
  value,
  onChange,
  placeholder = 'Select...',
  disabled = false,
  className,
  size = 'default',
  searchThreshold = 8,
}: SearchableSelectProps) {
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState('');
  const [activeIdx, setActiveIdx] = React.useState(0);
  const rootRef = React.useRef<HTMLDivElement | null>(null);
  const inputRef = React.useRef<HTMLInputElement | null>(null);
  const listRef = React.useRef<HTMLUListElement | null>(null);

  const showSearch = options.length > searchThreshold;

  const selected = options.find((o) => o.value === value);
  const selectedLabel = selected?.label ?? '';

  const filtered = React.useMemo(() => {
    if (!query.trim()) return options;
    const q = query.toLowerCase();
    return options.filter(
      (o) => o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q),
    );
  }, [options, query]);

  React.useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  React.useEffect(() => {
    if (open && showSearch) {
      requestAnimationFrame(() => inputRef.current?.focus());
    }
    if (!open) setQuery('');
  }, [open, showSearch]);

  React.useEffect(() => {
    if (activeIdx >= filtered.length) setActiveIdx(Math.max(0, filtered.length - 1));
  }, [filtered.length, activeIdx]);

  const choose = (opt: SelectOption) => {
    if (opt.disabled) return;
    onChange?.(opt.value);
    setOpen(false);
  };

  const onTriggerKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
      e.preventDefault();
      setOpen(true);
    }
  };

  const onListKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIdx((i) => Math.min(filtered.length - 1, i + 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIdx((i) => Math.max(0, i - 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const opt = filtered[activeIdx];
      if (opt) choose(opt);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div ref={rootRef} className={cn('relative', className)}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => !disabled && setOpen((o) => !o)}
        onKeyDown={onTriggerKey}
        className={cn(
          'w-full flex items-center justify-between rounded-md border border-border bg-surface-raised text-text font-medium ring-offset-background transition-colors hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
          sizeClass[size],
        )}
      >
        <span className={cn('truncate text-left', !selectedLabel && 'text-text-muted')}>
          {selectedLabel || placeholder}
        </span>
        <ChevronDown className="h-4 w-4 text-text-muted shrink-0" />
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-full rounded-md border border-border bg-surface-raised shadow-lg">
          {showSearch && (
            <div className="flex items-center gap-2 border-b border-border px-2 py-1.5">
              <Search className="h-3.5 w-3.5 text-text-muted shrink-0" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => { setQuery(e.target.value); setActiveIdx(0); }}
                onKeyDown={onListKey}
                placeholder={`Search ${options.length} models...`}
                className="flex-1 bg-transparent text-xs text-text placeholder:text-text-muted focus:outline-none"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => { setQuery(''); inputRef.current?.focus(); }}
                  className="text-text-muted hover:text-text"
                  aria-label="Clear search"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          )}
          <ul
            ref={listRef}
            role="listbox"
            tabIndex={-1}
            onKeyDown={onListKey}
            className="max-h-72 overflow-y-auto py-1"
          >
            {filtered.length === 0 ? (
              <li className="px-3 py-2 text-xs text-text-muted">No matches</li>
            ) : (
              filtered.map((opt, i) => {
                const prevGroup = i > 0 ? filtered[i - 1]?.group : undefined;
                const showHeader = !!opt.group && opt.group !== prevGroup;
                return (
                  <React.Fragment key={opt.value}>
                    {showHeader && (
                      <li
                        role="presentation"
                        className="px-3 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-wide text-text-muted select-none"
                      >
                        {opt.group}
                      </li>
                    )}
                    <li
                      role="option"
                      aria-selected={opt.value === value}
                      onMouseEnter={() => setActiveIdx(i)}
                      onClick={() => choose(opt)}
                      className={cn(
                        'cursor-pointer px-3 py-1.5 text-xs truncate',
                        opt.disabled && 'opacity-50 cursor-not-allowed',
                        !opt.disabled && i === activeIdx && 'bg-primary/10 text-text',
                        !opt.disabled && i !== activeIdx && 'text-text hover:bg-surface',
                        opt.value === value && 'font-semibold',
                      )}
                    >
                      {opt.label}
                    </li>
                  </React.Fragment>
                );
              })
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
