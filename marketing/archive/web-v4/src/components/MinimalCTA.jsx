import React, { useState } from 'react';

export function MinimalCTA() {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState('idle');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!email || !email.includes('@')) return;
    setStatus('submitting');
    setTimeout(() => {
      setStatus('success');
    }, 500);
  };

  return (
    <section id="privacy" className="py-24 px-6 bg-[var(--color-surface)] border-b border-[var(--color-surface-muted)]">
      <div className="max-w-[var(--content-max-width)] mx-auto minimal-card p-10 sm:p-16 rounded-3xl grid grid-cols-1 lg:grid-cols-12 gap-10 items-center">
        <div className="lg:col-span-7 space-y-4 text-left">
          <div className="text-xs font-mono font-semibold uppercase tracking-widest text-[var(--color-brand-blue)]">
            Early Access Preview
          </div>
          <h2 className="text-3xl sm:text-4xl font-display font-extrabold text-[var(--color-ink)] tracking-tight">
            Ready for a smarter, private host?
          </h2>
          <p className="text-base text-[var(--color-ink-secondary)] leading-relaxed max-w-lg font-sans">
            Halbert runs locally on your Mac or Linux machine with Ollama. No subscription, no telemetry, and complete control over your system.
          </p>
        </div>

        <div className="lg:col-span-5 w-full">
          {status === 'success' ? (
            <div className="p-4 bg-[#F0FDF4] border border-[#BBF7D0] text-[#166534] text-sm font-medium rounded-xl text-center">
              ✓ Access request recorded. Check your inbox for upcoming release drops.
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-2">
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Enter your email…"
                className="flex-1 px-4 py-3 bg-[var(--color-surface-subtle)] border border-[var(--color-surface-muted)] text-sm text-[var(--color-ink)] placeholder-[var(--color-ink-tertiary)] rounded-xl focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-blue)]"
                required
              />
              <button
                type="submit"
                disabled={status === 'submitting'}
                className="px-6 py-3 bg-[var(--color-ink)] text-white text-sm font-semibold rounded-xl hover:bg-[var(--color-accent-hover)] transition-colors shrink-0 shadow-sm"
              >
                {status === 'submitting' ? '…' : 'Get Preview'}
              </button>
            </form>
          )}
        </div>
      </div>
    </section>
  );
}
