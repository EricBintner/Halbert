import React, { useState } from 'react';
import { InteractiveConsole } from './InteractiveConsole';

export function MinimalHero({ onSubscribe, waitlistRef }) {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState('idle');

  const handleFormSubmit = (e) => {
    e.preventDefault();
    if (!email || !email.includes('@')) return;
    setStatus('submitting');
    setTimeout(() => {
      setStatus('success');
      if (onSubscribe) onSubscribe(email);
    }, 500);
  };

  return (
    <section className="pt-20 pb-20 px-6 studio-glow border-b border-[var(--color-surface-muted)]">
      <div className="max-w-[var(--content-max-width)] mx-auto text-center space-y-8">
        {/* Eyebrow Pill */}
        <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-[var(--color-surface)] border border-[var(--color-surface-muted)] text-[12px] font-mono text-[var(--color-ink-secondary)] shadow-xs">
          <span className="w-2 h-2 rounded-full bg-[var(--color-brand-emerald)] animate-pulse" />
          <span>Local-First Host Intelligence Engine</span>
        </div>

        {/* Powerful Utility-First Headline */}
        <h1 className="text-4xl sm:text-6xl lg:text-[64px] font-display font-extrabold tracking-tight text-[var(--color-ink)] leading-[1.08] max-w-4xl mx-auto">
          I diagnose, remember, and protect your system.
        </h1>

        {/* Lean 2-Sentence Subhead */}
        <p className="text-lg sm:text-xl text-[var(--color-ink-secondary)] leading-relaxed max-w-2xl mx-auto font-sans font-normal">
          A local AI assistant with instant access to your system telemetry, configuration history, and 16,000 pages of technical documentation. Grounded, fast, and 100% private.
        </p>

        {/* Minimal Waitlist Form */}
        <div ref={waitlistRef} className="pt-2 max-w-md mx-auto">
          {status === 'success' ? (
            <div className="p-4 bg-[#F0FDF4] border border-[#BBF7D0] text-[#166534] text-sm font-medium rounded-xl text-center">
              ✓ You're on the early access list. We'll dispatch preview binaries directly to your inbox.
            </div>
          ) : (
            <form onSubmit={handleFormSubmit} className="flex flex-col sm:flex-row gap-2">
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Enter your email address…"
                className="flex-1 px-4 py-3 bg-[var(--color-surface)] border border-[var(--color-surface-muted)] text-sm text-[var(--color-ink)] placeholder-[var(--color-ink-tertiary)] rounded-xl focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-blue)] transition-all shadow-xs"
                required
              />
              <button
                type="submit"
                disabled={status === 'submitting'}
                className="px-6 py-3 bg-[var(--color-ink)] text-white text-sm font-semibold rounded-xl hover:bg-[var(--color-accent-hover)] transition-all shadow-sm active:translate-y-0.5 shrink-0"
              >
                {status === 'submitting' ? 'Submitting…' : 'Join Preview'}
              </button>
            </form>
          )}

          {/* Platform Commitment Badges */}
          <div className="pt-4 flex justify-center items-center space-x-6 text-[12px] font-mono text-[var(--color-ink-tertiary)]">
            <span>● 100% Local (Ollama)</span>
            <span>● macOS &amp; Linux</span>
            <span>● Zero Cloud Telemetry</span>
          </div>
        </div>

        {/* Live Interactive Desktop Console Preview */}
        <div id="console" className="pt-8">
          <InteractiveConsole />
        </div>
      </div>
    </section>
  );
}
