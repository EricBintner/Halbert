import React, { useState } from 'react';
import { HalbertMark } from './HalbertMark';

export function EditorialColophon() {
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
    <footer id="colophon" className="py-20 px-6 sm:px-12 bg-[var(--color-surface-subtle)] border-t border-white/20 text-white font-sans">
      <div className="max-w-[var(--content-max-width)] mx-auto space-y-16">
        {/* Postal Dispatch Subscription Plate */}
        <div className="editorial-plate p-8 sm:p-12 grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
          <div className="lg:col-span-7 space-y-3">
            <div className="text-xs font-mono text-[var(--color-accent)] font-bold uppercase tracking-widest">
              EARLY ACCESS REGISTRY // AUTUMN 2026
            </div>
            <h3 className="text-3xl sm:text-4xl font-display font-black text-white tracking-tight">
              Receive the first dispatch binaries.
            </h3>
            <p className="text-sm text-[var(--color-ink-secondary)] leading-relaxed max-w-lg">
              Halbert runs locally on your Mac or Linux desktop with Ollama. Zero telemetry leaves your machine. Enter your email to receive early access builds.
            </p>
          </div>

          <div className="lg:col-span-5">
            {status === 'success' ? (
              <div className="p-4 bg-[var(--color-surface)] border border-[var(--color-accent)] text-[var(--color-accent)] font-display font-bold text-sm">
                ✓ Recorded. Dispatch notices will arrive in your inbox.
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-0">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Enter your email…"
                  className="flex-1 px-4 py-3 bg-[var(--color-surface)] border border-white/30 text-white placeholder-white/50 text-sm focus:outline-none focus:border-[var(--color-accent)]"
                  required
                />
                <button
                  type="submit"
                  disabled={status === 'submitting'}
                  className="px-6 py-3 bg-[var(--color-accent)] text-[#1B447A] font-display font-bold text-xs uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition-colors shadow-md"
                >
                  {status === 'submitting' ? '…' : 'Register'}
                </button>
              </form>
            )}
          </div>
        </div>

        {/* Colophon Credits & Links */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 pt-8 border-t border-white/10 text-xs text-[var(--color-ink-secondary)]">
          <div className="space-y-3">
            <div className="flex items-center space-x-2.5">
              <HalbertMark size={24} color="#FFFFFF" />
              <span className="font-display font-bold text-xl text-white">
                Halbert<span className="text-[var(--color-accent)]">.</span>
              </span>
            </div>
            <p className="leading-relaxed font-sans">
              Local-first host intelligence system.<br />
              Published by Eric Bintner.<br />
              Set in Fraunces &amp; Instrument Serif.
            </p>
          </div>

          <div className="space-y-2">
            <div className="font-mono text-xs font-bold uppercase tracking-wider text-white">
              JOURNAL
            </div>
            <ul className="space-y-1.5 font-sans">
              <li><a href="#hero" className="hover:text-[var(--color-accent)]">Prologue</a></li>
              <li><a href="#chapters" className="hover:text-[var(--color-accent)]">The Chapters</a></li>
              <li><a href="#confessional" className="hover:text-[var(--color-accent)]">The Being</a></li>
            </ul>
          </div>

          <div className="space-y-2">
            <div className="font-mono text-xs font-bold uppercase tracking-wider text-white">
              ARCHITECTURE
            </div>
            <ul className="space-y-1.5 font-sans">
              <li>Tauri Desktop Host</li>
              <li>Ollama Local Model</li>
              <li>SourcePrep Grounding</li>
              <li>Polkit Isolation</li>
            </ul>
          </div>

          <div className="space-y-2">
            <div className="font-mono text-xs font-bold uppercase tracking-wider text-white">
              OPEN SOURCE
            </div>
            <p className="leading-relaxed font-sans">
              No cloud tracking. 100% XDG standard compliant.
            </p>
            <div className="pt-2">
              <a
                href="https://github.com/EricBintner/Halbert"
                target="_blank"
                rel="noreferrer"
                className="text-[var(--color-accent)] font-bold underline font-mono"
              >
                GitHub Repository →
              </a>
            </div>
          </div>
        </div>

        <div className="pt-6 border-t border-white/10 flex flex-col sm:flex-row justify-between items-center text-[11px] font-mono text-[var(--color-ink-tertiary)]">
          <div>FOLIO NO. 03 · RETRO SERIF EDITION</div>
          <div>© 2026 HALBERT PROJECT. ALL RIGHTS RESERVED.</div>
        </div>
      </div>
    </footer>
  );
}
