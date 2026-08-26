import React, { useState, useEffect } from 'react';
import { THEMES, applyTheme, getSavedTheme } from '../lib/themes';

export function ThemePicker({ defaultTheme = 'linen-violet' }) {
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
          className="px-3.5 py-2 bg-[#121417] text-white text-xs font-bold uppercase tracking-wider border-2 border-black shadow-xl hover:bg-[var(--color-violet-dark)] transition-all flex items-center space-x-2 cursor-pointer"
        >
          <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: currentTheme.preview.accent }} />
          <span>PALETTE: {currentTheme.name}</span>
          <span className="text-[10px] opacity-75">▾</span>
        </button>
      )}

      {/* Expanded Drawer */}
      {isOpen && (
        <div className="w-80 bg-white text-[#121417] border-2 border-black shadow-2xl p-5 space-y-4 text-xs font-mono">
          {/* Header */}
          <div className="flex justify-between items-baseline border-b border-black/20 pb-2.5">
            <div className="space-y-0.5">
              <div className="font-bold text-sm tracking-tight text-[#121417]">
                EXPERIMENTAL COLOR MATRIX
              </div>
              <div className="text-[10px] text-gray-600 uppercase">
                HOT-SWAP TOKENS &amp; SHADERS
              </div>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="text-sm font-bold px-1.5 py-0.5 hover:bg-gray-100 border border-black cursor-pointer"
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
                      ? 'border-2 border-black bg-indigo-50 font-bold shadow-xs'
                      : 'border-gray-300 hover:border-black bg-white'
                  }`}
                >
                  <div className="flex justify-between items-center mb-1">
                    <div className="font-bold text-xs">
                      {theme.name}
                    </div>
                    {/* Swatch */}
                    <div className="flex items-center space-x-1 p-0.5 border border-black/20">
                      <span className="w-3.5 h-3.5" style={{ backgroundColor: theme.preview.canvas }} />
                      <span className="w-3.5 h-3.5" style={{ backgroundColor: theme.preview.accent }} />
                    </div>
                  </div>
                  <div className="text-[10px] font-normal text-gray-700 font-sans">
                    {theme.description}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Action Footer */}
          <div className="pt-2 border-t border-black/20 flex justify-between items-center text-[10px]">
            <button
              onClick={handleCopyCSS}
              className="px-2.5 py-1 bg-[#121417] text-white font-bold uppercase hover:bg-[var(--color-violet-dark)] transition-colors cursor-pointer"
            >
              {copied ? '✓ COPIED' : 'COPY CSS TOKENS'}
            </button>
            <span className="text-gray-600">
              ACTIVE: <strong>{currentTheme.id}</strong>
            </span>
          </div>
        </div>
      )}
    </aside>
  );
}
