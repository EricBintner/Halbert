import React, { useState } from 'react';

export function ScrollyProductWindow() {
  const [activeStep, setActiveStep] = useState(0);

  const steps = [
    {
      id: 'sensors',
      badge: 'STAGE 01 // SENSORY INTAKE',
      title: 'I feel my own physical hardware.',
      overlay:
        'Continuous intake across 16 thermal diodes, fan RPMs, and storage wear. When a backup disk logs 3 uncorrectable timeouts at dawn, Halbert stages a proactive triage note before the drive fails.',
      cli: [
        { type: 'cmd', text: 'halbert vitals --deep' },
        { type: 'res', text: '● 16 Thermal Diodes: Nominal (avg 44.2°C)' },
        { type: 'res', text: '● NVMe /dev/nvme0n1: 100% Health, 0 Bad Sectors' },
        { type: 'warn', text: '▲ Warning: /dev/sda1 logged 3 read timeouts during mirror sync' },
        { type: 'info', text: '→ Triage note created in local memory.' },
      ],
      tag: 'HARDWARE TELEMETRY',
    },
    {
      id: 'memory',
      badge: 'STAGE 02 // CONFIGURATION ARCHAEOLOGY',
      title: 'I remember why you made that change.',
      overlay:
        'Traditional tools lose human intent the second you close the editor. Halbert preserves human rationale alongside configuration AST diffs. Never wonder why SSH was moved to port 2222.',
      cli: [
        { type: 'cmd', text: 'halbert rationale /etc/ssh/sshd_config' },
        { type: 'res', text: 'AST Diff: Port 22 -> Port 2222 (Modified: July 14, 2026)' },
        { type: 'res', text: 'Reason: Automated brute-force scanners flooding auth log (4.2k/day)' },
        { type: 'info', text: 'Provenance verified in SQLite host memory.' },
      ],
      tag: 'AST INTENT RECORD',
    },
    {
      id: 'safety',
      badge: 'STAGE 03 // GROUNDED RAG & POLKIT GATE',
      title: 'I propose safe dry-runs. You approve.',
      overlay:
        'Halbert indexes 16,000 system man pages and operating system guides with local SourcePrep RAG. Every proposal includes blast-radius isolation and requires explicit Polkit authorization.',
      cli: [
        { type: 'cmd', text: 'halbert propose storage-compress /data --dry-run' },
        { type: 'res', text: 'Action: mount -o remount,compression=lz4 /data' },
        { type: 'res', text: 'Blast Radius: LOW (Live remount, zero unmount downtime)' },
        { type: 'res', text: 'Estimated Space Recovery: 35% (bcachefs lz4)' },
        { type: 'prompt', text: '[ Grant Polkit Authorization ] [ Cancel ]' },
      ],
      tag: 'POLKIT ISOLATION',
    },
  ];

  const current = steps[activeStep];

  return (
    <section className="full-window-section relative py-20 px-6 sm:px-12 bg-[#F0EDE6] border-b border-[var(--color-surface-muted)] aged-grit text-[var(--color-ink)]">
      {/* Top Section Folio Header */}
      <div className="max-w-6xl mx-auto w-full flex justify-between items-center text-xs font-mono text-[var(--color-ink-secondary)] border-b border-black/20 pb-3 mb-10">
        <div className="flex items-center space-x-3">
          <span className="font-bold text-[var(--color-ink)]">FULL-WINDOW EXPERIENCE 01</span>
          <span className="text-[var(--color-ink-tertiary)]">// PRODUCT IN ACTION</span>
        </div>
        <div className="text-[11px] font-bold uppercase tracking-widest text-[var(--color-violet-dark)]">
          AUTONOMOUS LOCAL RUNTIME
        </div>
      </div>

      <div className="max-w-6xl mx-auto w-full grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
        {/* Left Column: Interactive Stage Scrollytelling Overlay */}
        <div className="lg:col-span-5 space-y-6 text-left">
          {/* Step Badges */}
          <div className="flex space-x-2">
            {steps.map((s, idx) => (
              <button
                key={s.id}
                onClick={() => setActiveStep(idx)}
                className={`px-3 py-1.5 text-xs font-mono font-bold transition-all cursor-pointer ${
                  activeStep === idx
                    ? 'bg-[#121417] text-white shadow-sm'
                    : 'bg-white/80 text-[var(--color-ink-secondary)] hover:bg-white border border-black/15'
                }`}
              >
                0{idx + 1}
              </button>
            ))}
          </div>

          <div className="text-xs font-mono font-bold tracking-widest text-[var(--color-violet-dark)] uppercase">
            {current.badge}
          </div>

          <h2 className="text-3xl sm:text-5xl font-display font-black text-[var(--color-ink)] tracking-tight leading-[1.05] cmyk-bleed">
            {current.title}
          </h2>

          <p className="text-base sm:text-lg text-[var(--color-ink-secondary)] leading-relaxed font-sans">
            {current.overlay}
          </p>

          <div className="pt-2">
            <span className="inline-block px-3 py-1 bg-white border border-black/20 text-xs font-mono font-semibold text-[var(--color-ink)]">
              {current.tag}
            </span>
          </div>
        </div>

        {/* Right Column: Authentic Desktop Window & Live Terminal */}
        <div className="lg:col-span-7 w-full">
          <div className="bg-[#121417] text-white border-2 border-black rounded-lg shadow-2xl overflow-hidden font-mono cmyk-box-bleed">
            {/* Titlebar */}
            <div className="h-10 px-4 bg-[#1E293B] border-b border-white/10 flex items-center justify-between select-none">
              <div className="flex items-center space-x-2">
                <span className="w-3 h-3 rounded-full bg-[#EF4444]" />
                <span className="w-3 h-3 rounded-full bg-[#F59E0B]" />
                <span className="w-3 h-3 rounded-full bg-[#10B981]" />
                <span className="text-xs text-white/60 ml-2">halbert-core // local session</span>
              </div>
              <div className="text-[10px] text-white/50">100% LOCAL (OLLAMA)</div>
            </div>

            {/* Live Terminal Content */}
            <div className="p-6 sm:p-8 space-y-4 text-xs sm:text-[13px] leading-relaxed">
              {current.cli.map((line, idx) => {
                if (line.type === 'cmd') {
                  return (
                    <div key={idx} className="flex items-start space-x-2 text-[var(--color-cmyk-cyan)] font-bold">
                      <span className="text-white/40">&gt;</span>
                      <span>{line.text}</span>
                    </div>
                  );
                }
                if (line.type === 'warn') {
                  return (
                    <div key={idx} className="p-2.5 bg-[#FEF3C7]/10 border border-[#F59E0B] text-[#FBBF24]">
                      {line.text}
                    </div>
                  );
                }
                if (line.type === 'prompt') {
                  return (
                    <div key={idx} className="pt-3 border-t border-white/15 flex flex-wrap gap-2">
                      <button className="px-3 py-1.5 bg-[#10B981] text-black font-bold uppercase text-[11px] hover:bg-[#34D399] transition-colors cursor-pointer">
                        [ AUTHORIZE WITH POLKIT ]
                      </button>
                      <button className="px-3 py-1.5 bg-white/10 text-white text-[11px] hover:bg-white/20">
                        [ DISMISS ]
                      </button>
                    </div>
                  );
                }
                return (
                  <div key={idx} className="text-white/80 pl-4 border-l border-white/20">
                    {line.text}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
