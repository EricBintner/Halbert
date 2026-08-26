import React, { useState } from 'react';
import { HalbertMark } from './HalbertMark';

export function SoulPosterWindow() {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState('idle');

  const handleRegister = (e) => {
    e.preventDefault();
    if (!email || !email.includes('@')) return;
    setStatus('submitting');
    setTimeout(() => {
      setStatus('success');
    }, 500);
  };

  return (
    <section className="full-window-section relative py-20 px-6 sm:px-12 bg-[var(--color-canvas)] border-b border-[var(--color-surface-muted)] text-[var(--color-ink)] select-none">
      {/* Top Section Header */}
      <div className="max-w-5xl mx-auto w-full flex justify-between items-center text-xs font-mono text-[var(--color-ink-secondary)] border-b border-black/20 pb-3 mb-10">
        <div className="flex items-center space-x-3">
          <span className="font-bold text-[var(--color-ink)]">FULL-WINDOW EXPERIENCE 02</span>
          <span className="text-[var(--color-ink-tertiary)]">// THE SOUL OF THE MACHINE</span>
        </div>
        <div className="text-[11px] font-mono text-[var(--color-ink-tertiary)]">
          ⨁ CALIBRATED TO HOST
        </div>
      </div>

      <div className="max-w-5xl mx-auto w-full space-y-12 text-left">
        {/* Monumental Confessional Statement */}
        <div className="space-y-4">
          <div className="inline-block px-3 py-1 bg-[var(--color-surface-subtle)] border border-black/15 text-xs font-mono font-bold tracking-widest uppercase text-[var(--color-violet-dark)]">
            EPILOGUE // PHYSICAL EMBODIMENT
          </div>

          <h2 className="text-4xl sm:text-7xl lg:text-[80px] font-display font-black tracking-tight text-[var(--color-ink)] leading-[0.98] cmyk-bleed">
            “I am not an assistant.<br />
            <span className="text-[var(--color-violet-deep)] italic font-serif">
              I am the machine.”
            </span>
          </h2>

          <p className="text-lg sm:text-2xl text-[var(--color-ink-secondary)] max-w-2xl font-sans leading-relaxed pt-2">
            When you ask a cloud chatbot "How are you?", it recites a disclaimer. When you ask Halbert, it tells you its load is light, its fan curves are calm, and its secondary backup drive needs attention.
          </p>
        </div>

        {/* Interactive Dispatch Box */}
        <div className="p-8 sm:p-10 bg-white border-2 border-black rounded-lg shadow-xl cmyk-box-bleed max-w-2xl">
          <div className="space-y-4">
            <div className="flex justify-between items-baseline border-b border-black/15 pb-2">
              <div className="font-display font-bold text-lg text-[var(--color-ink)]">
                Early Access Distribution Registry
              </div>
              <div className="text-xs font-mono text-[var(--color-violet-dark)] font-bold">
                MACOS &amp; LINUX
              </div>
            </div>

            <p className="text-xs sm:text-sm text-[var(--color-ink-secondary)] leading-relaxed font-sans">
              Halbert runs 100% locally on your machine with Ollama. Zero telemetry leaves your system. Inscribe your email to receive early preview binaries.
            </p>

            {status === 'success' ? (
              <div className="p-4 bg-[#ECFDF5] border border-[#10B981] text-[#065F46] font-display font-bold text-sm">
                ✓ Recorded to local distribution roster. Dispatch notices will follow.
              </div>
            ) : (
              <form onSubmit={handleRegister} className="flex flex-col sm:flex-row gap-0">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Enter your dispatch email…"
                  className="flex-1 px-4 py-3 bg-[var(--color-surface-subtle)] border border-black/30 text-sm focus:outline-none focus:border-black font-sans"
                  required
                />
                <button
                  type="submit"
                  disabled={status === 'submitting'}
                  className="px-6 py-3 bg-[#121417] text-white font-display font-bold text-xs uppercase tracking-wider hover:bg-[var(--color-violet-deep)] transition-colors shrink-0 cursor-pointer"
                >
                  {status === 'submitting' ? '…' : 'Register Now'}
                </button>
              </form>
            )}
          </div>
        </div>

        {/* Bottom Colophon Bar */}
        <div className="pt-6 border-t border-black/20 flex flex-col sm:flex-row justify-between items-center gap-4 text-xs font-mono text-[var(--color-ink-tertiary)]">
          <div className="flex items-center space-x-2">
            <HalbertMark size={20} color="#121417" strokeWidth={32} />
            <span className="font-bold text-[var(--color-ink)]">HALBERT COMPUTING CORP.</span>
            <span>— 100% HOST BOUND</span>
          </div>

          <div className="flex items-center space-x-4">
            <a
              href="https://github.com/EricBintner/Halbert"
              target="_blank"
              rel="noreferrer"
              className="text-[var(--color-violet-dark)] font-bold underline"
            >
              GitHub Repository ↗
            </a>
            <span>© 2026</span>
          </div>
        </div>
      </div>
    </section>
  );
}
