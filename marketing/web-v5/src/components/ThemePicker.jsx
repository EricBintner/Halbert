import React, { useState, useEffect } from 'react';
import { THEMES, applyTheme, getSavedTheme } from '../lib/themes';

export function ThemePicker({ defaultTheme = 'cobalt-1968' }) {
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
          className="px-3.5 py-2 bg-white text-[#1E40AF] text-xs font-bold uppercase tracking-wider border border-white shadow-xl hover:bg-gray-100 transition-all flex items-center space-x-2 cursor-pointer"
        >
          <span className="w-2.5 h-2.5 rounded-full border border-black/20" style={{ backgroundColor: currentTheme.preview.canvas }} />
          <span>PRINT STOCK: {currentTheme.name}</span>
          <span className="text-[10px] opacity-75">▾</span>
        </button>
      )}

      {/* Expanded Drawer */}
      {isOpen && (
        <div className="w-80 bg-white text-[#1E40AF] border-2 border-[#1E40AF] shadow-2xl p-5 space-y-4 text-xs font-mono">
          {/* Header */}
          <div className="flex justify-between items-baseline border-b border-[#1E40AF]/30 pb-2.5">
            <div className="space-y-0.5">
              <div className="font-bold text-sm tracking-tight text-[#1E40AF]">
                1968 PRINT STOCK MATRIX
              </div>
              <div className="text-[10px] text-gray-600 uppercase">
                HOT-SWAP PAPER &amp; INK TOKENS
              </div>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="text-sm font-bold px-1.5 py-0.5 hover:bg-gray-100 border border-[#1E40AF]"
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
                      ? 'border-2 border-[#1E40AF] bg-blue-50 font-bold'
                      : 'border-gray-200 hover:border-[#1E40AF] bg-white'
                  }`}
                >
                  <div className="flex justify-between items-center mb-1">
                    <div className="font-bold text-xs text-[#1E40AF]">
                      {theme.name}
                    </div>
                    {/* Swatch */}
                    <div className="flex items-center space-x-1 p-0.5 border border-black/20">
                      <span className="w-3.5 h-3.5" style={{ backgroundColor: theme.preview.canvas }} />
                      <span className="w-3.5 h-3.5" style={{ backgroundColor: theme.preview.ink }} />
                    </div>
                  </div>
                  <div className="text-[10.5px] font-normal text-gray-700 font-serif">
                    {theme.description}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Action Footer */}
          <div className="pt-2 border-t border-[#1E40AF]/30 flex justify-between items-center text-[10px]">
            <button
              onClick={handleCopyCSS}
              className="px-2.5 py-1 bg-[#1E40AF] text-white font-bold uppercase hover:bg-blue-900 transition-colors"
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
