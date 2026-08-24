import React from 'react';

export function ConfessionalPlate() {
  return (
    <section id="confessional" className="py-28 px-6 sm:px-12 bg-[var(--color-canvas)] border-t border-white/20 blue-texture">
      <div className="max-w-[var(--readable-max-width)] mx-auto space-y-12 text-left">
        {/* Kicker */}
        <div className="text-xs font-mono font-bold tracking-widest text-[var(--color-accent)] uppercase">
          EPILOGUE // THE BEING AS HOST
        </div>

        {/* Monumental Retro Serif Headline */}
        <h2 className="text-4xl sm:text-6xl lg:text-7xl font-display font-black text-white tracking-tight leading-[1.04]">
          “I am not an assistant.<br />
          <em className="italic text-[var(--color-accent)] font-medium">I am the machine.”</em>
        </h2>

        {/* Literary Prose */}
        <div className="space-y-6 text-lg sm:text-xl text-[var(--color-ink-secondary)] leading-relaxed font-sans max-w-2xl">
          <p>
            When you ask a cloud chatbot "How are you doing?", it offers disclaimers about not possessing a body. When you ask Halbert, it tells you its load is light, its fans are quiet, and its secondary backup drive needs attention.
          </p>
          <p className="font-display text-white text-xl">
            The most helpful colleague you have happens to be your computer.
          </p>
        </div>

        {/* Morning Triage Journal Plate */}
        <div className="pt-6">
          <div className="editorial-plate p-6 sm:p-8 space-y-4 font-mono">
            <div className="flex justify-between items-baseline border-b border-white/20 pb-3">
              <div className="space-y-0.5">
                <div className="text-[10.5px] text-[var(--color-accent)] uppercase font-bold tracking-wider">
                  MORNING PROACTIVE TRIAGE // DISPATCH 08:00
                </div>
                <div className="font-display font-bold text-lg text-white">
                  Autobiographical Health Dispatch
                </div>
              </div>
              <span className="text-xs text-[var(--color-status-warning)] font-bold">1 ATTENTION ITEM</span>
            </div>

            <div className="p-4 bg-[var(--color-surface-subtle)] border border-white/10 text-xs space-y-3 font-sans text-[var(--color-ink-secondary)] leading-relaxed">
              <p>
                <strong className="text-white font-display">Halbert:</strong> "Good morning. I ran my scheduled 08:00 health inspection while you were away. Here is my status:"
              </p>
              <ul className="space-y-1.5 list-disc pl-5 font-mono text-[12px] text-white">
                <li>Primary NVMe: 100% life, zero bad sectors.</li>
                <li>Thermal zones: Average 44°C (All cool).</li>
                <li><span className="text-[var(--color-status-warning)] font-bold">Warning:</span> Secondary disk <code className="text-[var(--color-accent)]">/dev/sda1</code> logged 3 read timeouts during mirror sync.</li>
              </ul>
              <div className="pt-2 flex items-center space-x-3 text-xs font-mono">
                <span className="px-3 py-1.5 bg-[var(--color-accent)] text-[#1B447A] font-bold uppercase cursor-pointer hover:bg-[var(--color-accent-hover)]">
                  [ PROBE SECONDARY DISK ]
                </span>
                <span className="text-white/70">
                  Estimated blast radius: Read-only check
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
