import React, { useState } from 'react';

export function InteractiveConsole() {
  const [activeTab, setActiveTab] = useState('vitals');

  const capabilities = {
    vitals: {
      query: 'Check current thermal status and storage health.',
      answer: 'All 16 CPU thermal diodes are reading 44.2°C (well below throttle limit). Primary NVMe is healthy with 0 bad sectors. Secondary backup drive has 3 read timeouts staged for triage.',
      badge: 'LIVE SENSOR INTAKE · /sys/class/hwmon',
      status: '● SENSORS NOMINAL',
      statusColor: 'text-[#10B981] bg-[#ECFDF5] border-[#A7F3D0]',
    },
    config: {
      query: 'Why is SSH listening on port 2222?',
      answer: 'You moved SSH to port 2222 on July 14, 2026. The auth journal logged 4,200 automated scan attempts in 6 hours, so you hardened the daemon. Rationale is stored in configuration memory.',
      badge: 'AST DIFF · /etc/ssh/sshd_config.d/50-custom.conf',
      status: '● RATIONALE VERIFIED',
      statusColor: 'text-[#2563EB] bg-[#EFF6FF] border-[#BFDBFE]',
    },
    docs: {
      query: 'What is the syntax for live bcachefs compression?',
      answer: 'Use: `mount -o remount,compression=lz4 /data`. Bcachefs supports live in-place compression switches without unmounting. Benchmark sampling shows ~35% disk space recovery.',
      badge: 'SOURCEPREP RAG · 16,000 TECHNICAL MANUALS',
      status: '● DOC CITATION ATTACHED',
      statusColor: 'text-[#7C3AED] bg-[#F5F3FF] border-[#DDD6FE]',
    },
  };

  const current = capabilities[activeTab];

  return (
    <div className="max-w-3xl mx-auto minimal-card rounded-2xl overflow-hidden text-left font-sans">
      {/* Titlebar */}
      <div className="h-12 px-4 bg-[var(--color-surface-subtle)] border-b border-[var(--color-surface-muted)] flex items-center justify-between select-none">
        {/* Native traffic lights */}
        <div className="flex items-center space-x-2">
          <span className="w-3 h-3 rounded-full bg-[#FF5F56]" />
          <span className="w-3 h-3 rounded-full bg-[#FFBD2E]" />
          <span className="w-3 h-3 rounded-full bg-[#27C93F]" />
        </div>

        {/* Segmented Control Tabs */}
        <div className="flex items-center space-x-1 p-1 bg-[var(--color-surface-muted)]/70 rounded-lg text-xs font-medium text-[var(--color-ink-secondary)]">
          <button
            onClick={() => setActiveTab('vitals')}
            className={`px-3 py-1 rounded-md transition-all ${
              activeTab === 'vitals'
                ? 'bg-[var(--color-surface)] text-[var(--color-ink)] shadow-xs font-semibold'
                : 'hover:text-[var(--color-ink)]'
            }`}
          >
            Diagnostics
          </button>
          <button
            onClick={() => setActiveTab('config')}
            className={`px-3 py-1 rounded-md transition-all ${
              activeTab === 'config'
                ? 'bg-[var(--color-surface)] text-[var(--color-ink)] shadow-xs font-semibold'
                : 'hover:text-[var(--color-ink)]'
            }`}
          >
            Config Memory
          </button>
          <button
            onClick={() => setActiveTab('docs')}
            className={`px-3 py-1 rounded-md transition-all ${
              activeTab === 'docs'
                ? 'bg-[var(--color-surface)] text-[var(--color-ink)] shadow-xs font-semibold'
                : 'hover:text-[var(--color-ink)]'
            }`}
          >
            Manuals RAG
          </button>
        </div>

        {/* Host ID */}
        <div className="text-[11px] font-mono text-[var(--color-ink-tertiary)] hidden sm:inline">
          ubuntu-server-01
        </div>
      </div>

      {/* Console Content */}
      <div className="p-6 sm:p-8 space-y-5 bg-[var(--color-surface)]">
        {/* Query */}
        <div className="flex items-start space-x-3">
          <span className="text-[var(--color-brand-blue)] font-mono font-bold text-base">&gt;</span>
          <div className="font-semibold text-[var(--color-ink)] text-base">
            "{current.query}"
          </div>
        </div>

        {/* Halbert Response */}
        <div className="p-4 rounded-xl bg-[var(--color-surface-subtle)] border border-[var(--color-surface-muted)] text-sm text-[var(--color-ink)] leading-relaxed space-y-3">
          <div>
            <strong className="text-[var(--color-brand-blue)] font-mono font-semibold mr-1">HALBERT:</strong>
            {current.answer}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-[var(--color-surface-muted)] text-xs font-mono">
            <span className="text-[var(--color-ink-secondary)]">{current.badge}</span>
            <span className={`px-2 py-0.5 rounded-full border text-[11px] font-medium ${current.statusColor}`}>
              {current.status}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
