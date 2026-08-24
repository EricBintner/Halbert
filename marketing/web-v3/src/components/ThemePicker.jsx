import React, { useState, useEffect } from 'react';
import { THEMES, applyTheme, getSavedTheme } from '../lib/themes';

export function ThemePicker({ defaultTheme = 'aegean-blue' }) {
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
          className="px-3.5 py-2 bg-[var(--color-surface)] text-white text-xs font-bold uppercase tracking-wider border border-white/30 shadow-[0_8px_24px_rgba(0,0,0,0.4)] hover:bg-[var(--color-accent)] hover:text-[#1B447A] transition-all flex items-center space-x-2"
        >
          <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: currentTheme.preview.accent }} />
          <span>PALETTE: {currentTheme.name}</span>
          <span className="text-[10px] opacity-75">▾</span>
        </button>
      )}

      {/* Expanded Theme Drawer */}
      {isOpen && (
        <div className="w-80 sm:w-96 bg-[var(--color-surface)] border border-white/30 shadow-[0_20px_50px_rgba(0,0,0,0.6)] p-5 space-y-4 text-xs text-white">
          {/* Header */}
          <div className="flex justify-between items-baseline border-b border-white/20 pb-2.5">
            <div className="space-y-0.5">
              <div className="font-display font-bold text-sm tracking-tight text-white">
                EDITORIAL COLOR MATRIX
              </div>
              <div className="text-[10px] text-[var(--color-ink-tertiary)] uppercase">
                HOT-SWAP THEME VARIABLES
              </div>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="text-sm font-bold px-1.5 py-0.5 hover:bg-white/10 border border-white/20"
            >
              ✕
            </button>
          </div>

          {/* Theme List */}
          <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
            {THEMES.map((theme) => {
              const isSelected = activeThemeId === theme.id;
              return (
                <div
                  key={theme.id}
                  onClick={() => handleSelectTheme(theme.id)}
                  className={`p-3 border transition-all cursor-pointer ${
                    isSelected
                      ? 'border-[var(--color-accent)] bg-[var(--color-surface-subtle)] shadow-md'
                      : 'border-white/15 bg-[var(--color-surface)] hover:border-white/40 hover:bg-[var(--color-surface-subtle)]'
                  }`}
                >
                  <div className="flex justify-between items-center mb-1">
                    <div className="font-bold text-xs text-white font-display">
                      {theme.name}
                    </div>
                    {/* Swatch */}
                    <div className="flex items-center space-x-1 p-0.5 bg-black/30 border border-white/20">
                      <span className="w-3.5 h-3.5" style={{ backgroundColor: theme.preview.canvas }} title="Canvas" />
                      <span className="w-3.5 h-3.5" style={{ backgroundColor: theme.preview.ink }} title="Ink" />
                      <span className="w-3.5 h-3.5" style={{ backgroundColor: theme.preview.accent }} title="Accent" />
                    </div>
                  </div>
                  <div className="text-[10px] text-[var(--color-ink-secondary)] font-sans">
                    {theme.era} · {theme.description}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Action Footer */}
          <div className="pt-2 border-t border-white/20 flex justify-between items-center text-[10px]">
            <button
              onClick={handleCopyCSS}
              className="px-2.5 py-1 bg-[var(--color-accent)] text-[#1B447A] font-bold uppercase hover:bg-white transition-colors"
            >
              {copied ? '✓ COPIED' : 'COPY CSS TOKENS'}
            </button>
            <span className="text-[var(--color-ink-tertiary)]">
              ACTIVE: <strong className="text-white">{currentTheme.id}</strong>
            </span>
          </div>
        </div>
      )}
    </aside>
  );
}
