import React, { useState } from 'react';
import { HalbertMark } from './HalbertMark';

export function ManifestFooter() {
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
    <footer id="manifest" className="py-20 px-4 sm:px-8 bg-[var(--color-canvas)] text-[var(--color-ink)] font-mono text-xs">
      <div className="max-w-[var(--content-max-width)] mx-auto space-y-16">
        {/* Technical Dispatch Box */}
        <div className="border-2 border-[var(--color-ink)] bg-[var(--color-surface)] p-8 sm:p-12 shadow-[8px_8px_0px_0px_rgba(18,20,23,1)] grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
          <div className="lg:col-span-7 space-y-3">
            <div className="text-[11px] font-bold text-[var(--color-accent)] uppercase tracking-widest">
              SYSTEM MANIFEST // EARLY FLIGHT DISPATCH
            </div>
            <h3 className="text-2xl sm:text-4xl font-display font-black text-[var(--color-ink)] tracking-tight">
              REGISTER YOUR HOST FOR PREVIEW ACCESS.
            </h3>
            <p className="text-sm text-[var(--color-ink-secondary)] leading-relaxed font-sans max-w-lg">
              Halbert runs locally on macOS and Linux with zero external cloud dependencies. Your system logs, configuration history, and sensory data never leave your host.
            </p>
          </div>

          <div className="lg:col-span-5">
            {status === 'success' ? (
              <div className="p-4 bg-[var(--color-ink)] text-white border-2 border-[var(--color-ink)]">
                ✓ Host recorded in dispatch manifest. Watch your inbox for access keys.
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-0">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="admin@local-server.lan"
                  className="flex-1 px-4 py-3 bg-[var(--color-canvas)] border-2 border-[var(--color-ink)] text-xs text-[var(--color-ink)] placeholder-[var(--color-ink-tertiary)] focus:outline-none"
                  required
                />
                <button
                  type="submit"
                  disabled={status === 'submitting'}
                  className="px-6 py-3 bg-[var(--color-accent)] text-white border-2 border-[var(--color-ink)] sm:border-l-0 font-bold uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition-colors shadow-[2px_2px_0px_0px_rgba(18,20,23,1)]"
                >
                  {status === 'submitting' ? '…' : 'Register'}
                </button>
              </form>
            )}
          </div>
        </div>

        {/* Technical Colophon & Links */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 pt-8 border-t-2 border-[var(--color-ink)] text-[11px] text-[var(--color-ink-secondary)]">
          <div className="space-y-2">
            <div className="flex items-center space-x-2">
              <HalbertMark size={22} color="#121417" />
              <span className="font-display font-black text-lg text-[var(--color-ink)]">
                HALBERT<span className="text-[var(--color-accent)] font-bold">.</span>
              </span>
            </div>
            <p className="leading-relaxed">
              Local-first host intelligence system.<br />
              Published by Eric Bintner.
            </p>
          </div>

          <div className="space-y-2">
            <div className="font-bold text-[var(--color-ink)] uppercase">ARCHITECTURE</div>
            <ul className="space-y-1">
              <li>Haloysius Mind Spine</li>
              <li>SourcePrep Awareness</li>
              <li>Tauri Desktop Engine</li>
              <li>Ollama Local Inference</li>
            </ul>
          </div>

          <div className="space-y-2">
            <div className="font-bold text-[var(--color-ink)] uppercase">COMMITMENT</div>
            <p className="leading-relaxed">
              100% XDG Base Directory standard.<br />
              Zero telemetry collection.<br />
              Auditable open-source core.
            </p>
          </div>

          <div className="space-y-2">
            <div className="font-bold text-[var(--color-ink)] uppercase">RESOURCES</div>
            <ul className="space-y-1">
              <li>
                <a href="https://github.com/EricBintner/Halbert" target="_blank" rel="noreferrer" className="text-[var(--color-ink)] underline font-bold hover:text-[var(--color-accent)]">
                  GitHub Repository →
                </a>
              </li>
              <li><a href="#hero" className="hover:text-[var(--color-ink)]">Host Ethos</a></li>
              <li><a href="#autobiography" className="hover:text-[var(--color-ink)]">Memory Tape</a></li>
            </ul>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row justify-between items-center text-[10.5px] text-[var(--color-ink-tertiary)] border-t border-[var(--color-ink)]/15 pt-6">
          <div>SPECIFICATION REV 2026.8 · SWISS DRAFTING FORMAT</div>
          <div>© 2026 HALBERT PROJECT. ALL RIGHTS RESERVED.</div>
        </div>
      </div>
    </footer>
  );
}
