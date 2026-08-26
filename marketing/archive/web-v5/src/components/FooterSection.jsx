import React, { useState } from 'react';
import { HalbertMark } from './HalbertMark';

export function FooterSection() {
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
    <footer className="py-20 px-6 sm:px-10 bg-[var(--color-canvas)] text-white font-sans text-left">
      <div className="max-w-[var(--content-max-width)] mx-auto space-y-16">
        {/* Early Access Banner */}
        <div className="graphic-box p-8 sm:p-12 grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
          <div className="lg:col-span-7 space-y-3">
            <div className="text-xs font-mono font-bold text-[var(--color-accent-amber)] uppercase tracking-widest">
              EARLY ACCESS DISTRIBUTION // 2026
            </div>
            <h3 className="text-3xl sm:text-4xl font-display font-black text-white tracking-tight">
              Get the local desktop binaries.
            </h3>
            <p className="text-sm text-[var(--color-ink-secondary)] leading-relaxed max-w-lg">
              Halbert runs locally on your Mac or Linux desktop with Ollama. Zero telemetry leaves your machine. Enter your email to receive early release drops.
            </p>
          </div>

          <div className="lg:col-span-5 w-full">
            {status === 'success' ? (
              <div className="p-4 bg-black/20 border border-[var(--color-accent-amber)] text-[var(--color-accent-amber)] font-display font-bold text-sm">
                ✓ Recorded to Early Distribution Roster.
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-0">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Enter your email…"
                  className="flex-1 px-4 py-3 bg-[#152E6F]/70 border border-white/40 text-white placeholder-white/50 text-sm focus:outline-none focus:border-white font-sans"
                  required
                />
                <button
                  type="submit"
                  disabled={status === 'submitting'}
                  className="px-6 py-3 bg-white text-[#1D4ED8] font-display font-bold text-xs uppercase tracking-wider hover:bg-[var(--color-accent-amber)] transition-colors shrink-0 shadow-md cursor-pointer"
                >
                  {status === 'submitting' ? '…' : 'Register'}
                </button>
              </form>
            )}
          </div>
        </div>

        {/* Links & Colophon Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-8 pt-8 border-t border-white/20 text-xs text-white/80">
          <div className="space-y-3">
            <div className="flex items-center space-x-2.5">
              <HalbertMark size={24} color="#FFFFFF" strokeWidth={32} />
              <span className="font-display font-bold text-xl text-white">
                Halbert<span className="text-[var(--color-accent-amber)]">.</span>
              </span>
            </div>
            <p className="leading-relaxed">
              Local-first host intelligence system.<br />
              Published by Eric Bintner.
            </p>
          </div>

          <div className="space-y-2 font-mono">
            <div className="text-white font-bold uppercase tracking-wider text-xs">
              NAVIGATION
            </div>
            <ul className="space-y-1 text-white/80 font-sans text-xs">
              <li><a href="#features" className="hover:text-white">01 / Sensations</a></li>
              <li><a href="#memory" className="hover:text-white">02 / Memory</a></li>
              <li><a href="#manuals" className="hover:text-white">03 / Manuals</a></li>
              <li><a href="#privacy" className="hover:text-white">04 / Local Host</a></li>
            </ul>
          </div>

          <div className="space-y-2 font-mono">
            <div className="text-white font-bold uppercase tracking-wider text-xs">
              ARCHITECTURE
            </div>
            <ul className="space-y-1 text-white/80 font-sans text-xs">
              <li>Tauri Desktop Container</li>
              <li>Ollama Local Weights</li>
              <li>SourcePrep Grounding</li>
              <li>Polkit Privilege Isolation</li>
            </ul>
          </div>

          <div className="space-y-2 font-mono">
            <div className="text-white font-bold uppercase tracking-wider text-xs">
              SOURCE
            </div>
            <p className="text-white/80 font-sans text-xs leading-relaxed">
              100% XDG standard compliant. Free and open source.
            </p>
            <div className="pt-2">
              <a
                href="https://github.com/EricBintner/Halbert"
                target="_blank"
                rel="noreferrer"
                className="text-[var(--color-accent-amber)] font-bold underline"
              >
                GitHub Repository →
              </a>
            </div>
          </div>
        </div>

        <div className="pt-6 border-t border-white/20 flex flex-col sm:flex-row justify-between items-center text-[11px] font-mono text-white/60">
          <div>HALBERT HOST INTELLIGENCE // 1960s GRAPHIC EDITION</div>
          <div>© 2026 HALBERT PROJECT. ALL RIGHTS RESERVED.</div>
        </div>
      </div>
    </footer>
  );
}
