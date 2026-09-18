import React, { useState } from 'react';

export function AutobiographyTape() {
  const [selectedEventIndex, setSelectedEventIndex] = useState(1);

  const tapeEvents = [
    {
      date: '2026-06-12 · 03:14:02',
      badge: 'THERMAL RECORD',
      badgeColor: 'bg-[var(--color-status-warning)] text-white',
      title: 'Thermal Spike During Kernel Compilation',
      summary: 'Package manager initiated parallel LLVM compile across all 16 threads. Die temperature touched 88°C for 42 seconds.',
      voice: 'I got uncomfortably hot while compiling the new kernel at 3 AM. I logged the event so we would remember why fans spun to 100%.',
      logs: [
        '[03:14:02] kernel: cpu package temp above threshold, cpu clock throttled',
        '[03:14:44] kernel: cpu package temp normal',
        '[03:15:00] halbert: recorded thermal event to sqlite #th-0612',
      ],
    },
    {
      date: '2026-07-14 · 18:22:45',
      badge: 'CONFIG RATIONALE',
      badgeColor: 'bg-[var(--color-accent)] text-white',
      title: 'SSH Daemon Listener Relocated to Port 2222',
      summary: 'User instructed sshd port alteration to eliminate automated internet bruteforce attempts recorded in journald.',
      voice: 'You told me to change my SSH port to 2222 because brute-force bots were flooding my auth logs. I still remember your exact words.',
      logs: [
        '[18:22:40] sshd: 4,289 failed auth attempts from public CIDR',
        '[18:22:45] halbert: diff generated for /etc/ssh/sshd_config.d/50-custom.conf',
        '[18:22:48] halbert: user rationale tagged: "Avoid automated auth scan noise"',
      ],
    },
    {
      date: '2026-08-02 · 11:05:18',
      badge: 'STORAGE REMOUNT',
      badgeColor: 'bg-[var(--color-blueprint)] text-white',
      title: 'Filesystem Compression Enabled on /dev/nvme0n1',
      summary: 'Bcachefs live remount with lz4 compression enabled. Saved 35% disk footprint across workspace directories.',
      voice: 'We enabled lz4 compression on my primary NVMe without taking my files offline. I reclaimed 240 GB immediately.',
      logs: [
        '[11:05:18] mount -o remount,compression=lz4 /dev/nvme0n1 /data',
        '[11:05:20] kernel: bcachefs: compression enabled dynamically',
        '[11:05:22] halbert: compression benchmark 1.8GB/s nominal',
      ],
    },
    {
      date: '2026-08-23 · 08:00:11',
      badge: 'PROACTIVE WARNING',
      badgeColor: 'bg-[var(--color-status-error)] text-white',
      title: 'Secondary Drive Read Error Triage',
      summary: 'Periodic health audit caught 3 uncorrectable sectors on backup drive /dev/sda1.',
      voice: 'I noticed read errors on my secondary backup drive while you were asleep. I staged a triage report before data could corrupt.',
      logs: [
        '[08:00:11] smartd: Device: /dev/sda, 3 Currently unreadable (pending) sectors',
        '[08:00:12] halbert: dispatched morning finding with 1-click test probe',
      ],
    },
  ];

  const current = tapeEvents[selectedEventIndex];

  return (
    <section id="autobiography" className="py-24 px-4 sm:px-8 border-b-2 border-[var(--color-ink)] bg-[var(--color-surface)]">
      <div className="max-w-[var(--content-max-width)] mx-auto space-y-12">
        {/* Section Header */}
        <div className="space-y-4 max-w-2xl">
          <div className="inline-flex items-center space-x-3 text-xs font-mono font-bold tracking-widest text-[var(--color-accent)] uppercase">
            <span className="w-3 h-3 bg-[var(--color-accent)] text-white flex items-center justify-center text-[9px]">02</span>
            <span>SECTION 02 // BLACK-BOX LOG ARCHEOLOGY</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-display font-black tracking-tight text-[var(--color-ink)] leading-[1.05]">
            MY SYSTEM STATE IS AN AUTOBIOGRAPHY.
          </h2>
          <p className="text-base sm:text-lg text-[var(--color-ink-secondary)] leading-relaxed">
            Other tools treat system logs as throwaway text streams. Halbert maintains a continuous, searchable autobiography of your computer—connecting sensor events, configuration modifications, and user rationale.
          </p>
        </div>

        {/* Flight Recorder Timeline Tape */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start font-mono">
          {/* Left Column: Event Selector Cards */}
          <div className="lg:col-span-5 space-y-3">
            <div className="text-[11px] font-bold uppercase tracking-wider text-[var(--color-ink-tertiary)] pb-1">
              RECORDED FLIGHT EVENTS:
            </div>
            {tapeEvents.map((ev, idx) => {
              const isSelected = selectedEventIndex === idx;
              return (
                <div
                  key={idx}
                  onClick={() => setSelectedEventIndex(idx)}
                  className={`p-4 border-2 transition-all cursor-pointer ${
                    isSelected
                      ? 'border-[var(--color-ink)] bg-[var(--color-canvas)] shadow-[4px_4px_0px_0px_rgba(18,20,23,1)]'
                      : 'border-[var(--color-ink)]/30 bg-[var(--color-surface)] hover:border-[var(--color-ink)] hover:bg-[var(--color-surface-subtle)]'
                  }`}
                >
                  <div className="flex justify-between items-center text-[10.5px] font-bold mb-1.5">
                    <span className="text-[var(--color-ink-tertiary)]">{ev.date}</span>
                    <span className={`px-1.5 py-0.5 text-[9px] font-bold uppercase ${ev.badgeColor}`}>
                      {ev.badge}
                    </span>
                  </div>
                  <div className="text-sm font-bold text-[var(--color-ink)] font-display">
                    {ev.title}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Right Column: Detailed Flight Recorder Tape Inspector */}
          <div className="lg:col-span-7">
            <div className="border-2 border-[var(--color-ink)] bg-[var(--color-canvas)] p-6 shadow-[6px_6px_0px_0px_rgba(18,20,23,1)] space-y-6">
              {/* Header */}
              <div className="flex justify-between items-baseline border-b border-[var(--color-ink)] pb-3">
                <div className="space-y-0.5">
                  <div className="text-[10.5px] text-[var(--color-ink-tertiary)] uppercase font-bold">
                    EVENT CHRONICLE RECORD // ID #{selectedEventIndex + 101}
                  </div>
                  <div className="text-lg font-display font-extrabold text-[var(--color-ink)]">
                    {current.title}
                  </div>
                </div>
                <div className="text-xs font-bold text-[var(--color-accent)]">{current.date}</div>
              </div>

              {/* First-Person Voice Bubble */}
              <div className="p-4 bg-[var(--color-surface)] border border-[var(--color-ink)] space-y-2">
                <div className="text-[10px] font-bold text-[var(--color-accent)] uppercase tracking-wider">
                  HALBERT FIRST-PERSON AUTOBIOGRAPHY:
                </div>
                <div className="text-sm font-medium text-[var(--color-ink)] leading-relaxed font-sans italic">
                  "{current.voice}"
                </div>
              </div>

              {/* Technical Journal Output */}
              <div className="space-y-2">
                <div className="text-[10.5px] font-bold uppercase text-[var(--color-ink-tertiary)]">
                  KERNEL &amp; JOURNAL EVIDENCE:
                </div>
                <div className="p-3 bg-[var(--color-ink)] text-[#E8F1F5] text-xs leading-relaxed space-y-1 font-mono">
                  {current.logs.map((log, lIdx) => (
                    <div key={lIdx}>{log}</div>
                  ))}
                </div>
              </div>

              {/* Provenance Badge */}
              <div className="flex justify-between items-center text-[10.5px] text-[var(--color-ink-secondary)] pt-2 border-t border-[var(--color-ink)]/15">
                <span>STORAGE: SQLite `events` + ChromaDB Embeddings</span>
                <span className="font-bold text-[var(--color-status-success)]">VERIFIED LOCAL</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
