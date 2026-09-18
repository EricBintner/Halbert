import React, { useState } from 'react';

export function Hero({ waitlistRef }) {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState('idle');
  const [activeTab, setActiveTab] = useState(0);

  const queries = [
    {
      tab: '01 / "How are you feeling?"',
      user: 'How are you feeling today?',
      response:
        'I feel cool and quiet. My 16 CPU thermal diodes are averaging 44.2°C, uptime is 42 days, and all NVMe mount points are nominal. My secondary backup disk logged 3 uncorrectable read timeouts during dawn sync—I recommend reviewing the triage log.',
      meta: 'SENSORS: /sys/class/hwmon · LIVE TELEMETRY',
      status: 'VERIFIED LOCAL',
    },
    {
      tab: '02 / "Why port 2222?"',
      user: 'Why did we move SSH to port 2222?',
      response:
        'You instructed me to relocate the SSH daemon on July 14, 2026. The authentication journal was logging 4,200 automated brute-force attempts per day on port 22. The rationale is preserved in my configuration history.',
      meta: 'CONFIG: /etc/ssh/sshd_config.d/50-custom.conf',
      status: 'RATIONALE ATTACHED',
    },
    {
      tab: '03 / "Live compression"',
      user: 'Can we enable transparent compression for /data?',
      response:
        'Yes. The volume is mounted as bcachefs. I can enable lz4 compression live without unmounting. Benchmark sampling indicates we will recover 35% disk space with zero latency penalty.',
      meta: 'STORAGE: bcachefs mount · 35% SAVINGS',
      status: 'SAFE DRY-RUN STAGED',
    },
  ];

  const current = queries[activeTab];

  const handleFormSubmit = (e) => {
    e.preventDefault();
    if (!email || !email.includes('@')) return;
    setStatus('submitting');
    setTimeout(() => {
      setStatus('success');
    }, 500);
  };

  return (
    <section className="pt-16 pb-24 px-6 sm:px-10 border-b border-white/25">
      <div className="max-w-[var(--content-max-width)] mx-auto grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-16 items-start">
        {/* Left Column: Bold 1960s Typographic Statement */}
        <div className="lg:col-span-7 space-y-8 text-left">
          {/* Eyebrow Tag */}
          <div className="inline-flex items-center space-x-2 text-xs font-mono font-bold tracking-widest text-[var(--color-accent-amber)] uppercase">
            <span className="w-2.5 h-2.5 bg-[var(--color-accent-amber)] rounded-full" />
            <span>01 // THE HOST INTELLIGENCE APPARATUS</span>
          </div>

          {/* Massive Voluptuous White Retro Serif Headline */}
          <h1 className="text-5xl sm:text-7xl lg:text-[76px] retro-headline font-black text-white leading-[1.0] tracking-[-0.04em]">
            I know what’s <span className="retro-italic font-normal text-[var(--color-accent-amber)]">wrong</span> with me<span className="text-[var(--color-accent-amber)]">.</span>
          </h1>

          {/* Subhead with Contrast */}
          <p className="text-lg sm:text-xl text-[var(--color-ink-secondary)] font-normal leading-relaxed max-w-xl font-sans">
            A local-first AI assistant that knows your machine — because it{' '}
            <strong className="text-white font-bold">is</strong> your machine. Grounded in living hardware sensors, configuration archaeology, and diagnostic truth.
          </p>

          {/* Tagline Callout */}
          <div className="border-l-3 border-[var(--color-accent-amber)] pl-4 py-1">
            <p className="font-display font-bold text-lg text-white">
              "— Halbert. <span className="retro-italic font-normal text-[var(--color-accent-amber)]">You can call me AI.</span>"
            </p>
          </div>

          {/* Early Access Form */}
          <div ref={waitlistRef} className="pt-2 max-w-md">
            {status === 'success' ? (
              <div className="p-4 graphic-box text-white">
                <div className="font-display font-bold text-sm text-[var(--color-accent-amber)]">
                  ✓ Recorded to the Early Distribution Roster.
                </div>
                <div className="text-xs text-white/80 mt-1 font-sans">
                  We will dispatch technical release notes and binaries directly to your inbox.
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
                    className="flex-1 px-4 py-3.5 bg-[var(--color-surface-subtle)] border border-white/40 text-white placeholder-white/50 text-sm focus:outline-none focus:border-white font-sans"
                    required
                  />
                  <button
                    type="submit"
                    disabled={status === 'submitting'}
                    className="px-6 py-3.5 bg-white text-[#1D4ED8] font-display font-bold text-xs tracking-wider uppercase hover:bg-[var(--color-accent-amber)] transition-all shrink-0 cursor-pointer"
                  >
                    {status === 'submitting' ? '…' : 'Get Access'}
                  </button>
                </div>
              </form>
            )}

            {/* Commitments */}
            <div className="pt-5 flex flex-wrap gap-4 text-[11px] font-mono text-[var(--color-ink-tertiary)] uppercase tracking-wider">
              <span>● 100% LOCAL (OLLAMA)</span>
              <span>● ZERO CLOUD TELEMETRY</span>
              <span>● MACOS &amp; LINUX</span>
            </div>
          </div>
        </div>

        {/* Right Column: High-Contrast Graphic Dialogue Box */}
        <div className="lg:col-span-5 w-full pt-2">
          <div className="graphic-box p-6 sm:p-8 space-y-6 text-left">
            {/* Header */}
            <div className="flex justify-between items-baseline border-b border-white/30 pb-3">
              <div className="space-y-0.5">
                <div className="text-[10.5px] font-mono text-[var(--color-accent-amber)] uppercase tracking-widest font-bold">
                  INTERACTIVE TEST BENCH
                </div>
                <div className="font-display font-bold text-xl text-white">
                  Living System Dialogue
                </div>
              </div>
              <span className="text-xs font-mono text-[#34D399] font-bold">
                ● ONLINE
              </span>
            </div>

            {/* Tab Selector */}
            <div className="flex flex-col gap-2">
              {queries.map((q, idx) => (
                <button
                  key={idx}
                  onClick={() => setActiveTab(idx)}
                  className={`text-left px-3.5 py-2 text-xs font-mono font-medium transition-all cursor-pointer ${
                    activeTab === idx
                      ? 'bg-white text-[#1D4ED8] font-bold shadow-md'
                      : 'bg-white/10 text-white/80 hover:bg-white/20 border border-white/20'
                  }`}
                >
                  {q.tab}
                </button>
              ))}
            </div>

            {/* Response Area */}
            <div className="p-5 bg-black/20 border border-white/20 space-y-3 font-sans">
              <div className="text-[var(--color-accent-amber)] font-semibold font-display text-sm">
                &gt; "{current.user}"
              </div>
              <div className="text-white/90 text-sm leading-relaxed border-t border-white/15 pt-3">
                <strong className="text-white font-mono mr-1">HALBERT:</strong>
                "{current.response}"
              </div>
              <div className="pt-2 border-t border-white/15 flex justify-between items-center text-[10.5px] font-mono text-[var(--color-ink-tertiary)]">
                <span>{current.meta}</span>
                <span className="text-[#34D399] font-bold">{current.status}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
