import React, { useState } from 'react';
import { Oscilloscope } from './Oscilloscope';

export function SwissHero({ onSubscribe, waitlistRef }) {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState('idle');
  const [activeQuery, setActiveQuery] = useState('temp');

  const queries = {
    temp: {
      question: 'How are you feeling right now?',
      answer: 'I feel great. My CPU temperature is 44°C, load average is 0.18, and all NVMe mount points have 100% life remaining.',
      proof: 'SOURCE: /sys/class/hwmon/hwmon2/temp1_input · HASH: #a98f12',
    },
    ssh: {
      question: 'Why is SSH listening on port 2222?',
      answer: 'On July 14, 2026, you moved my SSH listener to port 2222 because automated brute-force scans on port 22 were filling the auth journal.',
      proof: 'SOURCE: /etc/ssh/sshd_config.d/50-custom.conf · WHY ID: #wh-ssh-44',
    },
    backup: {
      question: 'Did the overnight backup succeed?',
      answer: 'Yes. My daily borg backup finished at 04:12 AM with 0 errors. 14.2 GB of incremental snapshots were committed.',
      proof: 'SOURCE: /var/log/borgmatic.log · EXIT: 0',
    },
  };

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
    <section id="hero" className="relative pt-12 pb-24 px-4 sm:px-8 border-b-2 border-[var(--color-ink)] drafting-grid">
      <div className="max-w-[var(--content-max-width)] mx-auto grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-16 items-start">
        {/* Left Column: Swiss Poster Typographic Architecture */}
        <div className="lg:col-span-7 space-y-8">
          {/* Section Marker */}
          <div className="inline-flex items-center space-x-3 text-xs font-mono font-bold tracking-widest text-[var(--color-accent)] uppercase">
            <span className="w-3 h-3 bg-[var(--color-accent)] text-white flex items-center justify-center text-[9px]">01</span>
            <span>SECTION 01 // PRINCIPLE OF EMBODIMENT</span>
          </div>

          {/* Headline */}
          <h1 className="text-4xl sm:text-5xl lg:text-[58px] font-display font-extrabold tracking-tighter text-[var(--color-ink)] leading-[1.03]">
            I RUN ON YOUR HARDWARE.<br />
            <span className="text-[var(--color-accent)]">I SPEAK IN FIRST PERSON.</span>
          </h1>

          {/* Body Prose */}
          <div className="space-y-4 text-base sm:text-lg text-[var(--color-ink-secondary)] leading-relaxed max-w-xl font-normal">
            <p>
              When an AI lives thousands of miles away in a cloud datacenter, it has no body. It cannot inspect thermal throttles, parse local configuration diffs, or remember why you moved a network port.
            </p>
            <p className="font-semibold text-[var(--color-ink)]">
              Halbert is not a cloud chatbot. Halbert is an AI that <em className="italic font-serif">is</em> your computer — grounded in local telemetry, configuration history, and diagnostic truth.
            </p>
          </div>

          {/* Direct Interactive Test Bar */}
          <div className="border-2 border-[var(--color-ink)] bg-[var(--color-surface)] p-4 shadow-[4px_4px_0px_0px_rgba(18,20,23,1)] space-y-3 font-mono">
            <div className="text-[11px] font-bold text-[var(--color-ink-tertiary)] uppercase flex justify-between">
              <span>TEST QUERY HALBERT LIVE:</span>
              <span className="text-[var(--color-accent)]">CLICK TO TEST</span>
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => setActiveQuery('temp')}
                className={`px-3 py-1.5 text-xs font-bold uppercase transition-all ${
                  activeQuery === 'temp'
                    ? 'bg-[var(--color-ink)] text-white'
                    : 'bg-[var(--color-surface-subtle)] text-[var(--color-ink)] border border-[var(--color-ink)] hover:bg-[var(--color-surface-muted)]'
                }`}
              >
                &gt; "How are you?"
              </button>
              <button
                onClick={() => setActiveQuery('ssh')}
                className={`px-3 py-1.5 text-xs font-bold uppercase transition-all ${
                  activeQuery === 'ssh'
                    ? 'bg-[var(--color-ink)] text-white'
                    : 'bg-[var(--color-surface-subtle)] text-[var(--color-ink)] border border-[var(--color-ink)] hover:bg-[var(--color-surface-muted)]'
                }`}
              >
                &gt; "Why port 2222?"
              </button>
              <button
                onClick={() => setActiveQuery('backup')}
                className={`px-3 py-1.5 text-xs font-bold uppercase transition-all ${
                  activeQuery === 'backup'
                    ? 'bg-[var(--color-ink)] text-white'
                    : 'bg-[var(--color-surface-subtle)] text-[var(--color-ink)] border border-[var(--color-ink)] hover:bg-[var(--color-surface-muted)]'
                }`}
              >
                &gt; "Overnight backup?"
              </button>
            </div>

            {/* Live Response Box */}
            <div className="p-3 bg-[var(--color-canvas)] border border-[var(--color-ink)] text-xs space-y-2 mt-2">
              <div className="text-[var(--color-ink-secondary)] font-bold">
                Q: {queries[activeQuery].question}
              </div>
              <div className="text-[var(--color-ink)] leading-relaxed font-bold">
                HALBERT: "{queries[activeQuery].answer}"
              </div>
              <div className="text-[10px] text-[var(--color-blueprint)] border-t border-[var(--color-ink)]/15 pt-1.5">
                {queries[activeQuery].proof}
              </div>
            </div>
          </div>

          {/* Early Access Manifest Input */}
          <div ref={waitlistRef} className="pt-2 max-w-lg font-mono">
            {status === 'success' ? (
              <div className="p-4 bg-[var(--color-ink)] text-white text-xs border-2 border-[var(--color-ink)] shadow-[4px_4px_0px_0px_rgba(230,92,0,1)]">
                ✓ MANIFEST RECORDED. DISPATCH NOTICE WILL ARRIVE VIA EMAIL.
              </div>
            ) : (
              <form onSubmit={handleFormSubmit} className="space-y-2">
                <div className="text-[11px] font-bold uppercase tracking-wider text-[var(--color-ink)]">
                  REGISTER PHYSICAL HOST FOR EARLY PREVIEW:
                </div>
                <div className="flex flex-col sm:flex-row gap-0">
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="sysadmin@hostname.org"
                    className="flex-1 px-4 py-3 bg-[var(--color-surface)] border-2 border-[var(--color-ink)] text-xs text-[var(--color-ink)] placeholder-[var(--color-ink-tertiary)] focus:outline-none focus:bg-[var(--color-surface-subtle)] font-mono"
                    required
                  />
                  <button
                    type="submit"
                    disabled={status === 'submitting'}
                    className="px-6 py-3 bg-[var(--color-accent)] text-white border-2 border-[var(--color-ink)] sm:border-l-0 text-xs font-bold uppercase tracking-widest hover:bg-[var(--color-accent-hover)] transition-colors shadow-[4px_4px_0px_0px_rgba(18,20,23,1)]"
                  >
                    {status === 'submitting' ? '…' : 'Join Manifest'}
                  </button>
                </div>
              </form>
            )}

            <div className="pt-4 flex flex-wrap gap-4 text-[10.5px] font-bold text-[var(--color-ink-tertiary)] uppercase tracking-wider">
              <span>● 100% LOCAL (OLLAMA)</span>
              <span>● ZERO CLOUD TELEMETRY</span>
              <span>● MACOS &amp; LINUX</span>
            </div>
          </div>
        </div>

        {/* Right Column: Oscilloscope & Telemetry Engine */}
        <div className="lg:col-span-5 w-full space-y-6 pt-4">
          <Oscilloscope />

          {/* Architectural Specifications Card */}
          <div className="border-2 border-[var(--color-ink)] bg-[var(--color-surface)] p-5 shadow-[4px_4px_0px_0px_rgba(18,20,23,1)] space-y-3 font-mono text-xs">
            <div className="font-bold uppercase tracking-wider text-[var(--color-ink)] border-b border-[var(--color-ink)] pb-2">
              SYSTEM ARCHITECTURE SPECIFICATIONS
            </div>
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div className="p-2 bg-[var(--color-surface-subtle)] border border-[var(--color-ink)]">
                <div className="text-[9.5px] text-[var(--color-ink-tertiary)]">REASONING ENGINE</div>
                <div className="font-bold text-[var(--color-ink)]">Haloysius Spine</div>
              </div>
              <div className="p-2 bg-[var(--color-surface-subtle)] border border-[var(--color-ink)]">
                <div className="text-[9.5px] text-[var(--color-ink-tertiary)]">RAG SUBSTRATE</div>
                <div className="font-bold text-[var(--color-ink)]">SourcePrep Native</div>
              </div>
              <div className="p-2 bg-[var(--color-surface-subtle)] border border-[var(--color-ink)]">
                <div className="text-[9.5px] text-[var(--color-ink-tertiary)]">MEMORY STORE</div>
                <div className="font-bold text-[var(--color-ink)]">SQLite + ChromaDB</div>
              </div>
              <div className="p-2 bg-[var(--color-surface-subtle)] border border-[var(--color-ink)]">
                <div className="text-[9.5px] text-[var(--color-ink-tertiary)]">ELEVATION LAYER</div>
                <div className="font-bold text-[var(--color-ink)]">Polkit Atomic Exec</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
