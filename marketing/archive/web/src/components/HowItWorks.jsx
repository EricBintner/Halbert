import React from 'react';
import { DesktopWindow } from './DesktopWindow';

export function HowItWorks({ copy }) {
  const spreads = copy?.spreads || [
    {
      figure: 'FIG. 1',
      kicker: 'PHYSIOLOGICAL SELF-AWARENESS',
      headline: 'I can feel my own temperature.',
      body: [
        'Generic AI assistants hallucinate system facts because they live in a data center thousands of miles away.',
        'I live here. I monitor my own CPU thermal zones, load averages, and drive wear in real time.',
        'When I tell you /dev/sda1 is logging read errors, it is not a hypothetical. It is my body.',
      ],
      caption: 'Continuous hwmon & kernel sensor telemetry loop.',
    },
    {
      figure: 'FIG. 2',
      kicker: 'INSTITUTIONAL MEMORY',
      headline: 'I remember why you changed that.',
      body: [
        'Why did you move SSH to port 2222 three months ago? Why is compression turned off on the data volume?',
        'I store the rationale alongside the configuration diff.',
        'You never have to guess who edited /etc/fstab or why. I remember every command you ever gave me.',
      ],
      caption: 'AST-aware configuration diff with historical user rationale.',
    },
    {
      figure: 'FIG. 3',
      kicker: 'CONVERSATIONAL SPRAY & PRAY IS OVER',
      headline: 'Don’t guess. Ask me.',
      body: [
        'You do not need to memorize 400 flags for journalctl or write fragile grep pipelines.',
        'Speak to me like a senior systems colleague. I check my own state, formulate safe dry-runs, and ask your permission before touching anything.',
      ],
      caption: 'Single conversation container with dynamic diagnostic proof.',
    },
  ];

  return (
    <section id="how-it-works" className="py-24 px-6 bg-[var(--color-canvas)]">
      <div className="max-w-[var(--content-max-width)] mx-auto space-y-32">
        {/* SPREAD 1: Sensor Physiology (FIG. 1) */}
        <div className="pt-8 border-t-3 border-[var(--color-ink)] grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-16 items-center">
          {/* Left: Copy Block */}
          <div className="lg:col-span-6 space-y-6">
            <div className="flex items-center space-x-3 text-xs font-mono font-bold tracking-widest text-[var(--color-accent)] uppercase">
              <span>{spreads[0].figure}</span>
              <span>—</span>
              <span>{spreads[0].kicker}</span>
            </div>
            <h2 className="text-4xl sm:text-5xl font-display font-extrabold text-[var(--color-ink)] tracking-tight leading-[1.08]">
              {spreads[0].headline}
            </h2>
            <div className="space-y-4 text-base sm:text-lg text-[var(--color-ink-secondary)] leading-relaxed">
              {spreads[0].body.map((p, i) => (
                <p key={i}>{p}</p>
              ))}
            </div>
            <div className="text-xs font-mono font-medium text-[var(--color-ink-tertiary)] border-t border-[var(--color-ink)]/20 pt-3">
              NOTE: {spreads[0].caption}
            </div>
          </div>

          {/* Right: Tactile 60s Sensor Gauge Unit */}
          <div className="lg:col-span-6 crop-marks">
            <div className="border-2 border-[var(--color-ink)] bg-[var(--color-surface)] p-6 shadow-[6px_6px_0px_0px_rgba(26,25,24,1)] space-y-6">
              <div className="flex justify-between items-center border-b-2 border-[var(--color-ink)] pb-3 font-mono text-xs font-bold uppercase">
                <span>READOUT: THERMAL &amp; COMPUTE MATRIX</span>
                <span className="text-[var(--color-status-success)]">● NOMINAL</span>
              </div>

              {/* Gauge Meters */}
              <div className="space-y-4 font-mono text-xs">
                <div>
                  <div className="flex justify-between text-xs font-bold mb-1">
                    <span>CPU TEMPERATURE (Tctl / Tdie)</span>
                    <span>45°C</span>
                  </div>
                  <div className="h-4 border border-[var(--color-ink)] bg-[var(--color-surface-subtle)] p-0.5">
                    <div className="h-full bg-[var(--color-status-success)] w-[45%]" />
                  </div>
                </div>

                <div>
                  <div className="flex justify-between text-xs font-bold mb-1">
                    <span>LOAD AVERAGE (1m, 5m, 15m)</span>
                    <span>0.15 · 0.22 · 0.18</span>
                  </div>
                  <div className="h-4 border border-[var(--color-ink)] bg-[var(--color-surface-subtle)] p-0.5">
                    <div className="h-full bg-[var(--color-ink)] w-[15%]" />
                  </div>
                </div>

                <div>
                  <div className="flex justify-between text-xs font-bold mb-1">
                    <span>PRIMARY NVMe HEALTH (/dev/nvme0n1)</span>
                    <span>100% HEALTHY</span>
                  </div>
                  <div className="h-4 border border-[var(--color-ink)] bg-[var(--color-surface-subtle)] p-0.5">
                    <div className="h-full bg-[var(--color-accent)] w-[42%]" />
                  </div>
                </div>
              </div>

              <div className="p-3 bg-[var(--color-surface-subtle)] border border-[var(--color-ink)] font-mono text-xs leading-relaxed text-[var(--color-ink)]">
                <strong>Halbert:</strong> "I feel cool and quiet. All 16 thermal diodes are operating 40°C below throttle limits."
              </div>
            </div>
          </div>
        </div>

        {/* SPREAD 2: Institutional Memory (FIG. 2) */}
        <div className="pt-8 border-t-3 border-[var(--color-ink)] grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-16 items-center">
          {/* Left: Config Diff Document */}
          <div className="lg:col-span-6 order-2 lg:order-1 crop-marks">
            <div className="border-2 border-[var(--color-ink)] bg-[var(--color-surface)] p-6 shadow-[6px_6px_0px_0px_rgba(26,25,24,1)] space-y-4 font-mono">
              <div className="flex justify-between items-center border-b-2 border-[var(--color-ink)] pb-3 text-xs font-bold uppercase">
                <span>DIFF: /etc/ssh/sshd_config.d/50-custom.conf</span>
                <span className="text-[var(--color-ink-tertiary)]">2026-07-14</span>
              </div>

              <div className="p-4 bg-[var(--color-surface-subtle)] border border-[var(--color-ink)] text-[13px] space-y-2 leading-relaxed">
                <div className="text-[var(--color-ink-tertiary)]"># Port Isolation Rule</div>
                <div className="text-[#C83E2D] bg-[#FDF2F0] px-2 py-0.5 border border-[#C83E2D]/30">- Port 22</div>
                <div className="text-[#2D7A56] bg-[#EEF6F2] px-2 py-0.5 border border-[#2D7A56]/30">+ Port 2222</div>
                <div className="pt-3 border-t border-[var(--color-ink)]/20 text-xs text-[var(--color-ink)]">
                  <span className="text-[var(--color-accent)] font-bold">RATIONALE:</span> "Moved port after auth log recorded 4,200 automated scan attempts in 6 hours."
                </div>
              </div>

              <div className="flex justify-between text-xs font-bold pt-1 text-[var(--color-ink-secondary)]">
                <span>BLAST RADIUS: REVERSIBLE</span>
                <span>STATUS: VERIFIED IN CHROMADB</span>
              </div>
            </div>
          </div>

          {/* Right: Copy Block */}
          <div className="lg:col-span-6 order-1 lg:order-2 space-y-6">
            <div className="flex items-center space-x-3 text-xs font-mono font-bold tracking-widest text-[var(--color-accent)] uppercase">
              <span>{spreads[1].figure}</span>
              <span>—</span>
              <span>{spreads[1].kicker}</span>
            </div>
            <h2 className="text-4xl sm:text-5xl font-display font-extrabold text-[var(--color-ink)] tracking-tight leading-[1.08]">
              {spreads[1].headline}
            </h2>
            <div className="space-y-4 text-base sm:text-lg text-[var(--color-ink-secondary)] leading-relaxed">
              {spreads[1].body.map((p, i) => (
                <p key={i}>{p}</p>
              ))}
            </div>
            <div className="text-xs font-mono font-medium text-[var(--color-ink-tertiary)] border-t border-[var(--color-ink)]/20 pt-3">
              NOTE: {spreads[1].caption}
            </div>
          </div>
        </div>

        {/* SPREAD 3: Conversation Container (FIG. 3) */}
        <div className="pt-8 border-t-3 border-[var(--color-ink)] grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-16 items-center">
          {/* Left: Copy Block */}
          <div className="lg:col-span-6 space-y-6">
            <div className="flex items-center space-x-3 text-xs font-mono font-bold tracking-widest text-[var(--color-accent)] uppercase">
              <span>{spreads[2].figure}</span>
              <span>—</span>
              <span>{spreads[2].kicker}</span>
            </div>
            <h2 className="text-4xl sm:text-5xl font-display font-extrabold text-[var(--color-ink)] tracking-tight leading-[1.08]">
              {spreads[2].headline}
            </h2>
            <div className="space-y-4 text-base sm:text-lg text-[var(--color-ink-secondary)] leading-relaxed">
              {spreads[2].body.map((p, i) => (
                <p key={i}>{p}</p>
              ))}
            </div>
            <div className="text-xs font-mono font-medium text-[var(--color-ink-tertiary)] border-t border-[var(--color-ink)]/20 pt-3">
              NOTE: {spreads[2].caption}
            </div>
          </div>

          {/* Right: Conversational UI Container */}
          <div className="lg:col-span-6 crop-marks">
            <DesktopWindow title="Halbert — Desktop Host" figure="FIG. 3" activeTab="storage">
              <div className="space-y-4 text-[13.5px]">
                <div className="flex items-start space-x-2 text-[var(--color-ink)] font-bold">
                  <span className="text-[var(--color-accent)]">&gt;</span>
                  <span>Can we enable compression on the data volume?</span>
                </div>

                <div className="p-4 bg-[var(--color-surface-subtle)] border border-[var(--color-ink)] text-[var(--color-ink)] leading-relaxed space-y-3">
                  <p>
                    I checked my <code className="font-bold text-[var(--color-accent)]">/etc/fstab</code>. I am currently mounted with compression off on <code className="font-bold">/dev/nvme0n1</code>.
                  </p>
                  <p>
                    Enabling <code className="font-bold">lz4</code> is safe for our workload and I can apply it live without unmounting. Shall I run a benchmark probe first?
                  </p>
                  <div className="pt-2 flex items-center space-x-2 text-xs">
                    <span className="px-2 py-1 bg-[var(--color-ink)] text-white font-bold">
                      [ APPROVE LIVE REMOUNT ]
                    </span>
                    <span className="px-2 py-1 bg-[var(--color-surface)] border border-[var(--color-ink)] font-bold">
                      [ RUN BENCHMARK FIRST ]
                    </span>
                  </div>
                </div>
              </div>
            </DesktopWindow>
          </div>
        </div>
      </div>
    </section>
  );
}
