import React, { useState, useEffect } from 'react';
import { THEMES, applyTheme, getSavedTheme } from '../lib/themes';

export function ThemePicker({ defaultTheme = 'chartreuse-teal' }) {
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
    <aside aria-label="Developer theme picker" className="fixed bottom-4 left-6 z-40 font-mono select-none">
      {/* Minimized Docked Pill */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="px-3.5 py-2 bg-[#115E59] text-white text-xs font-bold uppercase tracking-wider border border-[var(--color-vector-lime)] shadow-xl hover:bg-[var(--color-vector-lime)] hover:text-[#042F2E] transition-all flex items-center space-x-2 cursor-pointer"
        >
          <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: currentTheme.preview.accent }} />
          <span>PALETTE: {currentTheme.name}</span>
          <span className="text-[10px] opacity-75">▾</span>
        </button>
      )}

      {/* Expanded Drawer */}
      {isOpen && (
        <div className="w-80 bg-[#115E59] text-white border-2 border-[var(--color-vector-lime)] shadow-2xl p-5 space-y-4 text-xs font-mono">
          {/* Header */}
          <div className="flex justify-between items-baseline border-b border-white/20 pb-2.5">
            <div className="space-y-0.5">
              <div className="font-bold text-sm tracking-tight text-white">
                KINETIC PALETTE MATRIX
              </div>
              <div className="text-[10px] text-[var(--color-vector-lime)] uppercase">
                HOT-SWAP VECTOR SHADERS
              </div>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="text-sm font-bold px-1.5 py-0.5 hover:bg-white/20 border border-white/40 cursor-pointer"
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
                  className={`p-3 border transition-all cursor-pointer ${
                    isSelected
                      ? 'border-2 border-[var(--color-vector-lime)] bg-[#134E4A] font-bold shadow-xs'
                      : 'border-white/20 hover:border-white bg-[#115E59]'
                  }`}
                >
                  <div className="flex justify-between items-center mb-1">
                    <div className="font-bold text-xs">
                      {theme.name}
                    </div>
                    {/* Swatch */}
                    <div className="flex items-center space-x-1 p-0.5 border border-white/30">
                      <span className="w-3.5 h-3.5" style={{ backgroundColor: theme.preview.canvas }} />
                      <span className="w-3.5 h-3.5" style={{ backgroundColor: theme.preview.accent }} />
                    </div>
                  </div>
                  <div className="text-[10px] font-normal text-white/80 font-sans">
                    {theme.description}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Action Footer */}
          <div className="pt-2 border-t border-white/20 flex justify-between items-center text-[10px]">
            <button
              onClick={handleCopyCSS}
              className="px-2.5 py-1 bg-[var(--color-vector-lime)] text-[#042F2E] font-bold uppercase hover:bg-white transition-colors cursor-pointer"
            >
              {copied ? '✓ COPIED' : 'COPY CSS TOKENS'}
            </button>
            <span className="text-white/70">
              ACTIVE: <strong>{currentTheme.id}</strong>
            </span>
          </div>
        </div>
      )}
    </aside>
  );
}
