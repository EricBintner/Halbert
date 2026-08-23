import React, { useState } from 'react';
import { ArrowRight, CheckCircle2, ShieldCheck, BookOpen, Terminal } from 'lucide-react';

export function Footer() {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState('idle');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!email || !email.includes('@')) return;
    setStatus('submitting');
    setTimeout(() => {
      setStatus('success');
    }, 600);
  };

  return (
    <footer id="architecture" className="py-20 px-6 bg-[var(--color-canvas)] border-t border-[var(--color-hairline)] text-[var(--color-ink)]">
      <div className="max-w-[var(--content-max-width)] mx-auto space-y-16">
        {/* Top Section: Secondary Call-to-Action */}
        <div className="p-8 sm:p-12 rounded-3xl bg-[var(--color-surface)] border border-[var(--color-hairline-strong)] shadow-[var(--shadow-card)] grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
          <div className="lg:col-span-7 space-y-2">
            <h3 className="text-2xl sm:text-3xl font-display font-semibold text-[var(--color-ink)]">
              Be the first to speak with your machine<span className="text-[var(--color-accent)]">.</span>
            </h3>
            <p className="text-[15px] text-[var(--color-ink-secondary)] leading-relaxed max-w-lg">
              Halbert runs locally on your Mac or Linux desktop with Ollama. Your system logs and telemetry never leave your machine.
            </p>
          </div>

          <div className="lg:col-span-5">
            {status === 'success' ? (
              <div className="p-4 rounded-xl bg-[#EEF6F2] border border-[#C2E0D1] flex items-center space-x-3 text-[#2D7A56]">
                <CheckCircle2 className="w-5 h-5 shrink-0" />
                <span className="text-sm font-medium">You're on the early access list!</span>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="flex gap-2">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Enter your email…"
                  className="flex-1 px-4 py-2.5 rounded-xl bg-[var(--color-surface-subtle)] border border-[var(--color-hairline-strong)] text-[14px] text-[var(--color-ink)] placeholder-[var(--color-ink-tertiary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
                  required
                />
                <button
                  type="submit"
                  disabled={status === 'submitting'}
                  className="px-5 py-2.5 rounded-xl bg-[var(--color-accent)] text-white text-[14px] font-semibold hover:bg-[var(--color-accent-hover)] transition-all shrink-0 flex items-center space-x-1.5 shadow-sm"
                >
                  <span>{status === 'submitting' ? '…' : 'Get Access'}</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </form>
            )}
          </div>
        </div>

        {/* Bottom Section: Wordmark, Columns, Legal */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 pt-6 text-sm text-[var(--color-ink-secondary)]">
          {/* Brand Col */}
          <div className="col-span-2 md:col-span-1 space-y-3">
            <div className="font-display font-semibold text-xl text-[var(--color-ink)]">
              Halbert<span className="text-[var(--color-accent)] font-bold">.</span>
            </div>
            <p className="text-xs text-[var(--color-ink-tertiary)] leading-relaxed">
              Local-first host intelligence. Built with mid-century clarity and safety-first autonomy.
            </p>
          </div>

          {/* Product Col */}
          <div className="space-y-2.5">
            <div className="font-mono text-xs font-semibold uppercase tracking-wider text-[var(--color-ink)]">
              Product
            </div>
            <ul className="space-y-2 text-xs">
              <li><a href="#how-it-works" className="hover:text-[var(--color-ink)]">How It Works</a></li>
              <li><a href="#the-being" className="hover:text-[var(--color-ink)]">The Soul</a></li>
              <li><a href="https://github.com/EricBintner/Halbert" target="_blank" rel="noreferrer" className="hover:text-[var(--color-ink)]">GitHub Repository</a></li>
            </ul>
          </div>

          {/* Architecture Col */}
          <div className="space-y-2.5">
            <div className="font-mono text-xs font-semibold uppercase tracking-wider text-[var(--color-ink)]">
              Architecture
            </div>
            <ul className="space-y-2 text-xs">
              <li><span className="text-[var(--color-ink-secondary)]">Tauri Desktop Host</span></li>
              <li><span className="text-[var(--color-ink-secondary)]">Ollama Local LLM</span></li>
              <li><span className="text-[var(--color-ink-secondary)]">SourcePrep RAG Engine</span></li>
              <li><span className="text-[var(--color-ink-secondary)]">Polkit Privilege Layer</span></li>
            </ul>
          </div>

          {/* Legal / Local Col */}
          <div className="space-y-2.5">
            <div className="font-mono text-xs font-semibold uppercase tracking-wider text-[var(--color-ink)]">
              Commitment
            </div>
            <p className="text-xs text-[var(--color-ink-tertiary)] leading-relaxed">
              No cloud tracking. 100% XDG compliant. Open source core.
            </p>
            <div className="pt-2 text-xs text-[var(--color-ink-ghost)]">
              © 2026 Halbert Project.
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
