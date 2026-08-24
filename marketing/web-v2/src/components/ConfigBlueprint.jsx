import React, { useState } from 'react';

export function ConfigBlueprint() {
  const [activeConfig, setActiveConfig] = useState('ssh');

  const configs = {
    ssh: {
      path: '/etc/ssh/sshd_config.d/50-custom.conf',
      service: 'sshd.service',
      scope: 'Network Ingress',
      blastRadius: 'LOW · INCOMING SSH CONNECTIONS ONLY',
      rawDiff: [
        { type: 'old', text: '- Port 22' },
        { type: 'new', text: '+ Port 2222' },
        { type: 'new', text: '+ PermitRootLogin no' },
        { type: 'new', text: '+ PasswordAuthentication no' },
      ],
      rationale: 'User requested public internet port isolation and key-only auth enforcement to eliminate credential bruteforce attacks.',
      impact: 'Blocks port 22 scanner bots; active sessions remain uninterrupted until daemon reload.',
    },
    fstab: {
      path: '/etc/fstab',
      service: 'systemd-remount-fs.service',
      scope: 'Storage Mounts',
      blastRadius: 'MEDIUM · STORAGE SUBSYSTEM',
      rawDiff: [
        { type: 'old', text: '- UUID=4a2... /data bcachefs defaults 0 2' },
        { type: 'new', text: '+ UUID=4a2... /data bcachefs defaults,compression=lz4 0 2' },
      ],
      rationale: 'Enabled dynamic lz4 compression on primary scratch volume after storage capacity crossed 80%.',
      impact: 'Immediate 35% disk space recovery with zero read latency degradation.',
    },
    network: {
      path: '/etc/systemd/resolved.conf',
      service: 'systemd-resolved.service',
      scope: 'DNS Resolution',
      blastRadius: 'LOW · LOCAL DNS CACHE',
      rawDiff: [
        { type: 'old', text: '- DNS=192.168.1.1' },
        { type: 'new', text: '+ DNS=1.1.1.1 9.9.9.9' },
        { type: 'new', text: '+ DNSOverTLS=yes' },
      ],
      rationale: 'Switched to encrypted DNS-over-TLS to prevent ISP DNS hijacking on upstream gateway.',
      impact: 'All outbound socket DNS queries encrypted with TLS certificate validation.',
    },
  };

  const current = configs[activeConfig];

  return (
    <section id="blueprint" className="py-24 px-4 sm:px-8 border-b-2 border-[var(--color-ink)] bg-[var(--color-canvas)] drafting-grid-lg">
      <div className="max-w-[var(--content-max-width)] mx-auto space-y-12">
        {/* Section Header */}
        <div className="space-y-4 max-w-2xl">
          <div className="inline-flex items-center space-x-3 text-xs font-mono font-bold tracking-widest text-[var(--color-accent)] uppercase">
            <span className="w-3 h-3 bg-[var(--color-accent)] text-white flex items-center justify-center text-[9px]">03</span>
            <span>SECTION 03 // CONFIGURATION AS PHYSIOLOGY</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-display font-black tracking-tight text-[var(--color-ink)] leading-[1.05]">
            CONFIGURATION IS NOT CODE. IT IS MY LIVING ANATOMY.
          </h2>
          <p className="text-base sm:text-lg text-[var(--color-ink-secondary)] leading-relaxed">
            Generic LLMs blindly generate shell commands without understanding dependencies. Halbert models your configuration graph as a living physiology—calculating blast radiuses and anchoring every modification to human rationale.
          </p>
        </div>

        {/* Interactive Drafting Blueprint Stage */}
        <div className="border-2 border-[var(--color-ink)] bg-[var(--color-surface)] shadow-[6px_6px_0px_0px_rgba(18,20,23,1)] p-6 sm:p-8 space-y-6 font-mono">
          {/* Blueprint Navigation Bar */}
          <div className="flex flex-wrap items-center justify-between gap-4 border-b-2 border-[var(--color-ink)] pb-4">
            <div className="flex items-center space-x-2">
              <span className="w-3 h-3 bg-[var(--color-blueprint)]" />
              <span className="font-bold text-xs uppercase tracking-wider text-[var(--color-ink)]">
                BLUEPRINT SCHEMATIC EXPLORER:
              </span>
            </div>

            {/* Target Selectors */}
            <div className="flex gap-1.5 text-xs font-bold">
              <button
                onClick={() => setActiveConfig('ssh')}
                className={`px-3 py-1.5 border border-[var(--color-ink)] uppercase transition-all ${
                  activeConfig === 'ssh'
                    ? 'bg-[var(--color-blueprint)] text-white shadow-[2px_2px_0px_0px_rgba(18,20,23,1)]'
                    : 'bg-[var(--color-surface-subtle)] text-[var(--color-ink)] hover:bg-[var(--color-surface-muted)]'
                }`}
              >
                /etc/ssh/
              </button>
              <button
                onClick={() => setActiveConfig('fstab')}
                className={`px-3 py-1.5 border border-[var(--color-ink)] uppercase transition-all ${
                  activeConfig === 'fstab'
                    ? 'bg-[var(--color-blueprint)] text-white shadow-[2px_2px_0px_0px_rgba(18,20,23,1)]'
                    : 'bg-[var(--color-surface-subtle)] text-[var(--color-ink)] hover:bg-[var(--color-surface-muted)]'
                }`}
              >
                /etc/fstab
              </button>
              <button
                onClick={() => setActiveConfig('network')}
                className={`px-3 py-1.5 border border-[var(--color-ink)] uppercase transition-all ${
                  activeConfig === 'network'
                    ? 'bg-[var(--color-blueprint)] text-white shadow-[2px_2px_0px_0px_rgba(18,20,23,1)]'
                    : 'bg-[var(--color-surface-subtle)] text-[var(--color-ink)] hover:bg-[var(--color-surface-muted)]'
                }`}
              >
                /etc/systemd/
              </button>
            </div>
          </div>

          {/* Blueprint Layout Matrix */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
            {/* Left: AST Diff Document */}
            <div className="lg:col-span-7 space-y-4">
              <div className="flex justify-between items-center text-xs font-bold text-[var(--color-ink-tertiary)]">
                <span>TARGET FILE: {current.path}</span>
                <span>SYSTEMD UNIT: {current.service}</span>
              </div>

              <div className="p-4 bg-[var(--color-ink)] text-[#E8F1F5] text-xs space-y-1 border border-[var(--color-ink)] shadow-inner font-mono">
                <div className="text-[var(--color-ink-ghost)] pb-1"># Atomic Precedence Diff Model</div>
                {current.rawDiff.map((line, idx) => (
                  <div
                    key={idx}
                    className={
                      line.type === 'old'
                        ? 'text-[#FFA8A8] bg-[#421A1A]/80 px-1 py-0.5'
                        : 'text-[#9CE6B8] bg-[#1A3D28]/80 px-1 py-0.5 font-bold'
                    }
                  >
                    {line.text}
                  </div>
                ))}
              </div>

              <div className="p-3 bg-[var(--color-accent-tint)] border border-[var(--color-accent)] text-[var(--color-ink)] text-xs leading-relaxed space-y-1">
                <div className="font-bold text-[var(--color-accent)] uppercase text-[10px]">
                  HUMAN RATIONALE ANCHOR:
                </div>
                <div>"{current.rationale}"</div>
              </div>
            </div>

            {/* Right: Blast-Radius & Safety Shield */}
            <div className="lg:col-span-5 space-y-4">
              <div className="p-4 bg-[var(--color-surface-subtle)] border border-[var(--color-ink)] space-y-3">
                <div className="text-[10.5px] font-bold uppercase text-[var(--color-ink-tertiary)]">
                  SAFETY &amp; BLAST RADIUS AUDIT:
                </div>
                <div className="text-xs font-bold text-[var(--color-ink)]">
                  {current.blastRadius}
                </div>
                <div className="text-xs text-[var(--color-ink-secondary)] leading-relaxed">
                  {current.impact}
                </div>
              </div>

              <div className="p-4 bg-[var(--color-surface-subtle)] border border-[var(--color-ink)] space-y-2 text-xs">
                <div className="text-[10.5px] font-bold uppercase text-[var(--color-ink-tertiary)]">
                  ELEVATION GATE:
                </div>
                <div className="flex items-center space-x-2 text-[var(--color-status-success)] font-bold">
                  <span>✓ POLKIT SANDBOX ISOLATION</span>
                </div>
                <div className="text-[11px] text-[var(--color-ink-secondary)]">
                  FastAPI never runs as root. Atomic writes dispatched via authenticated setuid polkit helper.
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
