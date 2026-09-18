import React, { useState } from 'react';
import { HalbertMark } from './HalbertMark';

export function Footer({ copy }) {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState('idle');

  const colophon = copy?.colophon || {
    title: 'Halbert.',
    publisher: 'Published by Eric Bintner. Set in Jost and JetBrains Mono.',
    materials: 'Printed on warm archival paper, 2026. Open source core.',
    subscribePrompt: 'To receive dispatch notes and preview builds:',
    subscribeButton: 'Submit',
    legal: 'No cloud tracking. 100% XDG Base Directory compliant. All telemetry stays on your host.',
    trademark: 'Halbert is not affiliated with or endorsed by Apple, Microsoft, Canonical, Red Hat, the Linux Foundation, Meta, OpenAI, Anthropic, Google, or any other trademark holder referenced on this site. All trademarks are the property of their respective owners.',
    copyright: '© 2026 Halbert Project. All rights reserved.',
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!email || !email.includes('@')) return;
    setStatus('submitting');
    setTimeout(() => {
      setStatus('success');
    }, 500);
  };

  return (
    <footer id="architecture" className="py-20 px-6 bg-[var(--color-canvas)] border-t-3 border-[var(--color-ink)] text-[var(--color-ink)] font-mono">
      <div className="max-w-[var(--content-max-width)] mx-auto space-y-16">
        {/* Colophon & Subscription Strip */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-start">
          {/* Left: Colophon Block */}
          <div className="lg:col-span-6 space-y-4">
            <div className="flex items-center space-x-3">
              <HalbertMark size={28} color="var(--color-ink)" />
              <span className="font-display font-black text-2xl tracking-tighter text-[var(--color-ink)]">
                {colophon.title}
              </span>
            </div>
            <p className="text-xs text-[var(--color-ink-secondary)] leading-relaxed max-w-md">
              {colophon.publisher}<br />
              {colophon.materials}
            </p>
            <p className="text-xs text-[var(--color-ink-tertiary)] pt-2">
              {colophon.legal}
            </p>
          </div>

          {/* Right: Minimalist Single-Line Subscription Input */}
          <div className="lg:col-span-6 space-y-3">
            <div className="text-xs font-bold uppercase tracking-wider text-[var(--color-ink)]">
              {colophon.subscribePrompt}
            </div>
            {status === 'success' ? (
              <div className="p-3 bg-[var(--color-ink)] text-white text-xs border border-[var(--color-ink)]">
                ✓ Address recorded for build dispatch.
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-0">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@domain.com"
                  className="flex-1 px-4 py-2.5 bg-[var(--color-surface)] border-2 border-[var(--color-ink)] text-[var(--color-ink)] text-xs placeholder-[var(--color-ink-tertiary)] focus:outline-none"
                  required
                />
                <button
                  type="submit"
                  disabled={status === 'submitting'}
                  className="px-6 py-2.5 bg-[var(--color-ink)] text-white border-2 border-[var(--color-ink)] sm:border-l-0 text-xs font-bold uppercase tracking-wider hover:bg-[var(--color-accent)] transition-colors"
                >
                  {status === 'submitting' ? '…' : colophon.subscribeButton}
                </button>
              </form>
            )}
          </div>
        </div>

        {/* Bottom Rule & Copyright */}
        <div className="pt-8 border-t border-[var(--color-ink)]/20 flex flex-col gap-6 text-xs text-[var(--color-ink-tertiary)]">
          <div className="flex flex-col sm:flex-row justify-between items-baseline gap-4">
            <div className="flex space-x-6">
              <a href="https://github.com/EricBintner/Halbert" target="_blank" rel="noreferrer" className="text-[var(--color-ink)] font-bold hover:text-[var(--color-accent)] underline">
                GitHub
              </a>
              <a href="#how-it-works" className="text-[var(--color-ink)] font-bold hover:text-[var(--color-accent)] underline">
                Spreads
              </a>
              <a href="#the-being" className="text-[var(--color-ink)] font-bold hover:text-[var(--color-accent)] underline">
                The Being
              </a>
            </div>
            <div>{colophon.copyright}</div>
          </div>
          {colophon.trademark && (
            <p className="max-w-[var(--content-max-width)] leading-relaxed text-[var(--color-ink-tertiary)]/80">
              {colophon.trademark}
            </p>
          )}
        </div>
      </div>
    </footer>
  );
}
