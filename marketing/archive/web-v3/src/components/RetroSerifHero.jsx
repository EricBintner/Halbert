import React, { useState } from 'react';

export function RetroSerifHero({ onSubscribe, waitlistRef }) {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState('idle');
  const [selectedPrompt, setSelectedPrompt] = useState(0);

  const prompts = [
    {
      label: '01. "How are you doing?"',
      user: 'How are you feeling today?',
      halbert:
        'I feel cool and quiet. My CPU thermal diodes are reading 44°C, uptime is 42 days, and all NVMe mount points are nominal. My secondary backup volume has 3 uncorrectable sectors—I recommend reviewing the triage log.',
      meta: 'SENSORS: /sys/class/hwmon · LIVE TELEMETRY',
    },
    {
      label: '02. "Why port 2222?"',
      user: 'Why did we change SSH to port 2222?',
      halbert:
        'You instructed me to relocate SSH on July 14, 2026. Automated brute-force scanners on port 22 were flooding the auth journal with 4,200 failed attempts per day. The rationale is recorded in my configuration memory.',
      meta: 'CONFIG: /etc/ssh/sshd_config.d/50-custom.conf',
    },
    {
      label: '03. "Enable compression"',
      user: 'Can we turn on compression for /data?',
      halbert:
        'Yes. My /data volume is formatted as bcachefs. I can enable lz4 compression live without unmounting. Benchmark sampling indicates we will save 35% disk space with zero latency penalty.',
      meta: 'STORAGE: bcachefs mount · 35% SAVINGS',
    },
  ];

  const active = prompts[selectedPrompt];

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
    <section id="hero" className="relative pt-16 pb-28 px-6 sm:px-12 blue-texture border-b border-white/20">
      <div className="max-w-[var(--content-max-width)] mx-auto grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-16 items-start">
        {/* Left Column: Dramatic White Serif Typography */}
        <div className="lg:col-span-6 space-y-8 text-left">
          {/* Eyebrow */}
          <div className="inline-flex items-center space-x-2 text-xs font-mono font-bold tracking-widest text-[var(--color-accent)] uppercase">
            <span className="w-2 h-2 bg-[var(--color-accent)] rounded-full" />
            <span>PROLOGUE // THE SELF-IDENTIFYING HOST</span>
          </div>

          {/* Massive White Retro Serif Headline */}
          <h1 className="text-5xl sm:text-6xl lg:text-[70px] font-display font-black tracking-tight text-white leading-[1.03]">
            I know what’s wrong with me<span className="text-[var(--color-accent)]">.</span>
          </h1>

          {/* Subhead with Italic Contrast */}
          <p className="text-lg sm:text-xl text-[var(--color-ink-secondary)] font-normal leading-relaxed max-w-xl font-sans">
            A local-first AI assistant that knows your machine — because it{' '}
            <em className="font-display italic text-white font-medium">is</em> your machine.
            Grounded in living telemetry, configuration memory, and diagnostic proof.
          </p>

          {/* Tagline Callout */}
          <div className="pt-1 pb-1 border-l-2 border-[var(--color-accent)] pl-4">
            <p className="font-display font-medium text-lg text-white tracking-wide">
              "— Halbert. <em className="italic text-[var(--color-accent)]">You can call me AI.</em>"
            </p>
          </div>

          {/* Early Access Email Dispatch Form */}
          <div ref={waitlistRef} className="pt-4 max-w-md">
            {status === 'success' ? (
              <div className="p-4 bg-[var(--color-surface-subtle)] text-white border border-[var(--color-accent)] shadow-[0_4px_16px_rgba(252,211,77,0.2)]">
                <div className="font-display font-bold text-sm text-[var(--color-accent)]">
                  ✓ Recorded to the Early Edition Folio.
                </div>
                <div className="text-xs text-[var(--color-ink-secondary)] mt-1 font-sans">
                  We will dispatch release notes and access binaries directly to your inbox.
                </div>
              </div>
            ) : (
              <form onSubmit={handleFormSubmit} className="space-y-3">
                <div className="flex flex-col sm:flex-row gap-0">
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Enter your email address…"
                    className="flex-1 px-4 py-3.5 bg-[var(--color-surface-subtle)] border border-white/30 text-white placeholder-white/50 text-sm focus:outline-none focus:border-[var(--color-accent)] font-sans"
                    required
                  />
                  <button
                    type="submit"
                    disabled={status === 'submitting'}
                    className="px-6 py-3.5 bg-[var(--color-accent)] text-[#1B447A] font-display font-bold text-sm tracking-wider uppercase hover:bg-[var(--color-accent-hover)] transition-all shadow-[0_4px_16px_rgba(252,211,77,0.3)] shrink-0"
                  >
                    {status === 'submitting' ? '…' : 'Subscribe'}
                  </button>
                </div>
              </form>
            )}

            {/* Platform Commitments */}
            <div className="pt-6 flex flex-wrap gap-4 text-[11px] font-mono text-[var(--color-ink-tertiary)] uppercase tracking-wider">
              <span>● 100% LOCAL (OLLAMA)</span>
              <span>● ZERO CLOUD TELEMETRY</span>
              <span>● MACOS &amp; LINUX</span>
            </div>
          </div>
        </div>

        {/* Right Column: Framed Editorial Interactive Dialogue Plate */}
        <div className="lg:col-span-6 w-full pt-4">
          <div className="editorial-plate p-6 sm:p-8 space-y-6">
            {/* Header */}
            <div className="flex justify-between items-baseline border-b border-white/20 pb-3">
              <div className="space-y-0.5">
                <div className="text-[10.5px] font-mono text-[var(--color-accent)] uppercase tracking-widest font-bold">
                  FIGURE I · INTIMATE SYSTEM DIALOGUE
                </div>
                <div className="font-display font-bold text-xl text-white">
                  Live Conversational Spine
                </div>
              </div>
              <div className="text-xs font-mono text-[var(--color-status-success)] bg-black/20 px-2 py-0.5 border border-[var(--color-status-success)]/40">
                ● ONLINE
              </div>
            </div>

            {/* Prompt Selector Pills */}
            <div className="flex flex-wrap gap-2">
              {prompts.map((p, idx) => (
                <button
                  key={idx}
                  onClick={() => setSelectedPrompt(idx)}
                  className={`px-3 py-1.5 text-xs font-mono font-medium transition-all ${
                    selectedPrompt === idx
                      ? 'bg-[var(--color-accent)] text-[#1B447A] font-bold shadow-md'
                      : 'bg-[var(--color-surface-subtle)] text-white/80 hover:text-white border border-white/20'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>

            {/* Dialogue Stage */}
            <div className="p-5 bg-[var(--color-surface-subtle)] border border-white/20 space-y-4 font-sans text-sm">
              {/* User Prompt */}
              <div className="flex items-start space-x-2 text-[var(--color-accent)] font-medium">
                <span className="font-mono font-bold">&gt;</span>
                <span className="text-white font-semibold font-display text-base">
                  "{active.user}"
                </span>
              </div>

              {/* Halbert Response */}
              <div className="text-[var(--color-ink-secondary)] leading-relaxed font-sans text-[14.5px] border-t border-white/10 pt-3">
                <span className="text-[var(--color-accent)] font-mono font-bold mr-1">HALBERT:</span>
                "{active.halbert}"
              </div>

              {/* Provenance Footer */}
              <div className="pt-2 border-t border-white/10 text-[11px] font-mono text-[var(--color-ink-tertiary)] flex justify-between">
                <span>{active.meta}</span>
                <span className="text-[var(--color-status-success)] font-bold">VERIFIED LOCAL</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
