import React, { useState, useEffect } from 'react';
import { THEMES, applyTheme, getSavedTheme } from '../lib/themes';

export function ThemePicker({ defaultTheme = 'studio-light' }) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeThemeId, setActiveThemeId] = useState(() => getSavedTheme(defaultTheme));
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    applyTheme(activeThemeId);
  }, [activeThemeId]);

  const handleSelectTheme = (id) => {
    setActiveThemeId(id);
    applyTheme(id);
  };

  const handleCopyCSS = () => {
    const theme = THEMES.find((t) => t.id === activeThemeId) || THEMES[0];
    const cssString = `:root {\n${Object.entries(theme.tokens)
      .map(([k, v]) => `  ${k}: ${v};`)
      .join('\n')}\n}`;

    navigator.clipboard.writeText(cssString).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const currentTheme = THEMES.find((t) => t.id === activeThemeId) || THEMES[0];

  return (
    <aside aria-label="Developer theme picker" className="fixed bottom-4 right-4 z-50 font-mono select-none">
      {/* Minimized Docked Pill */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="px-3.5 py-2 bg-[var(--color-surface)] text-[var(--color-ink)] text-xs font-semibold rounded-full border border-[var(--color-surface-muted)] shadow-md hover:border-[var(--color-ink-ghost)] transition-all flex items-center space-x-2"
        >
          <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: currentTheme.preview.accent }} />
          <span>Theme: {currentTheme.name}</span>
          <span className="text-[10px] opacity-75">▾</span>
        </button>
      )}

      {/* Expanded Drawer */}
      {isOpen && (
        <div className="w-80 bg-[var(--color-surface)] border border-[var(--color-surface-muted)] rounded-2xl shadow-2xl p-5 space-y-4 text-xs text-[var(--color-ink)]">
          {/* Header */}
          <div className="flex justify-between items-baseline border-b border-[var(--color-surface-muted)] pb-2.5">
            <div className="space-y-0.5">
              <div className="font-display font-bold text-sm tracking-tight">
                Design System Palette
              </div>
              <div className="text-[10px] text-[var(--color-ink-tertiary)] uppercase font-mono">
                Hot-Swap Custom Variables
              </div>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="text-sm font-bold p-1 rounded-md hover:bg-[var(--color-surface-subtle)] text-[var(--color-ink-secondary)]"
            >
              ✕
            </button>
          </div>

          {/* Theme List */}
          <div className="space-y-2">
            {THEMES.map((theme) => {
              const isSelected = activeThemeId === theme.id;
              return (
                <div
                  key={theme.id}
                  onClick={() => handleSelectTheme(theme.id)}
                  className={`p-3 rounded-xl border transition-all cursor-pointer ${
                    isSelected
                      ? 'border-[var(--color-ink)] bg-[var(--color-surface-subtle)] shadow-xs'
                      : 'border-[var(--color-surface-muted)] bg-[var(--color-surface)] hover:border-[var(--color-ink-ghost)]'
                  }`}
                >
                  <div className="flex justify-between items-center mb-1">
                    <div className="font-bold text-xs font-display">
                      {theme.name}
                    </div>
                    {/* Swatches */}
                    <div className="flex items-center space-x-1 p-0.5 rounded-full bg-[var(--color-surface-subtle)] border border-[var(--color-surface-muted)]">
                      <span className="w-3 h-3 rounded-full border border-black/10" style={{ backgroundColor: theme.preview.canvas }} />
                      <span className="w-3 h-3 rounded-full" style={{ backgroundColor: theme.preview.ink }} />
                      <span className="w-3 h-3 rounded-full" style={{ backgroundColor: theme.preview.accent }} />
                    </div>
                  </div>
                  <div className="text-[10px] text-[var(--color-ink-secondary)] font-sans">
                    {theme.description}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Action Footer */}
          <div className="pt-2 border-t border-[var(--color-surface-muted)] flex justify-between items-center text-[10px]">
            <button
              onClick={handleCopyCSS}
              className="px-3 py-1 bg-[var(--color-ink)] text-white font-medium rounded-lg hover:bg-[var(--color-accent-hover)] transition-colors"
            >
              {copied ? '✓ Copied' : 'Copy CSS Tokens'}
            </button>
            <span className="text-[var(--color-ink-tertiary)] font-mono">
              Active: <strong>{currentTheme.id}</strong>
            </span>
          </div>
        </div>
      )}
    </aside>
  );
}
