import React, { useState } from 'react';

export function ProofConsole() {
  const [activeTest, setActiveTest] = useState(0);

  const tests = [
    {
      id: 'sensors',
      name: '01. SENSOR INTAKE AUDIT',
      query: 'Check core thermal envelopes and fan PWM curves.',
      steps: [
        { label: 'INTAKE', text: 'Queried /sys/class/hwmon/hwmon2 across 16 core thermal diodes.', status: 'ok' },
        { label: 'RAG CITATION', text: 'Matched kernel doc: Documentation/hwmon/coretemp.rst', status: 'ok' },
        { label: 'MEMORY HASH', text: 'SQLite self_health table: #thm-992-verified', status: 'ok' },
      ],
      output: 'I read all 16 thermal diodes. Core package temp is 44.2°C (max allowed 100°C). Fans are currently idling at 800 RPM. Everything is running cold.',
    },
    {
      id: 'drift',
      name: '02. CONFIG DRIFT & RATIONALE',
      query: 'Did anyone modify /etc/hosts without logging rationale?',
      steps: [
        { label: 'INTAKE', text: 'Parsed AST diff for /etc/hosts against Git shadow commit #a7e1.', status: 'ok' },
        { label: 'PROVENANCE', text: 'Located entry added 2026-08-19: "10.0.0.45 staging-db"', status: 'warn' },
        { label: 'WHY LOOKUP', text: 'Warning: Missing recorded rationale tag in ChromaDB #why-hosts.', status: 'warn' },
      ],
      output: 'I noticed an unannotated line in my /etc/hosts ("10.0.0.45 staging-db") added 5 days ago without an explanation. Would you like me to tag a reason for it now?',
    },
    {
      id: 'storage',
      name: '03. STORAGE COMPRESSION BENCH',
      query: 'Simulate lz4 compression savings across workspace partition.',
      steps: [
        { label: 'INTAKE', text: 'Sampled 10,000 blocks on /dev/nvme0n1 (/data mount point).', status: 'ok' },
        { label: 'BENCHMARK', text: 'lz4 throughput: 2.1 GB/s · Estimated ratio: 1.54x (35% savings).', status: 'ok' },
        { label: 'SAFETY CHECK', text: 'Confirmed bcachefs live remount does not require unmount.', status: 'ok' },
      ],
      output: 'I ran a live probe on /data. Enabling lz4 will reclaim ~280 GB with zero detectable latency penalty. I have staged a 1-click dry-run command for your review.',
    },
  ];

  const current = tests[activeTest];

  return (
    <section id="proof" className="py-24 px-4 sm:px-8 border-b-2 border-[var(--color-ink)] bg-[var(--color-surface)]">
      <div className="max-w-[var(--content-max-width)] mx-auto space-y-12">
        {/* Section Header */}
        <div className="space-y-4 max-w-2xl">
          <div className="inline-flex items-center space-x-3 text-xs font-mono font-bold tracking-widest text-[var(--color-accent)] uppercase">
            <span className="w-3 h-3 bg-[var(--color-accent)] text-white flex items-center justify-center text-[9px]">04</span>
            <span>SECTION 04 // THE LABORATORY PROOF BENCH</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-display font-black tracking-tight text-[var(--color-ink)] leading-[1.05]">
            NEVER TRUST AN LLM WITHOUT PROOF.
          </h2>
          <p className="text-base sm:text-lg text-[var(--color-ink-secondary)] leading-relaxed">
            Every statement Halbert makes is backed by the Law of Four Whys (Why Now, Why Care, Why So, Why Trust). Test the diagnostic proof engine live below.
          </p>
        </div>

        {/* Diagnostic Laboratory Bench */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start font-mono">
          {/* Left: Test Cases Tabs */}
          <div className="lg:col-span-4 space-y-2.5">
            <div className="text-[11px] font-bold uppercase tracking-wider text-[var(--color-ink-tertiary)] pb-1">
              SELECT PROOF BENCH TEST:
            </div>
            {tests.map((test, idx) => {
              const isSelected = activeTest === idx;
              return (
                <button
                  key={test.id}
                  onClick={() => setActiveTest(idx)}
                  className={`w-full text-left p-4 border-2 transition-all ${
                    isSelected
                      ? 'border-[var(--color-ink)] bg-[var(--color-canvas)] shadow-[4px_4px_0px_0px_rgba(18,20,23,1)] font-bold'
                      : 'border-[var(--color-ink)]/30 bg-[var(--color-surface)] hover:border-[var(--color-ink)] hover:bg-[var(--color-surface-subtle)]'
                  }`}
                >
                  <div className="text-xs uppercase text-[var(--color-ink)] font-display font-extrabold">
                    {test.name}
                  </div>
                  <div className="text-[11px] text-[var(--color-ink-secondary)] truncate mt-1">
                    "{test.query}"
                  </div>
                </button>
              );
            })}
          </div>

          {/* Right: Step-by-step Trace and Output */}
          <div className="lg:col-span-8">
            <div className="border-2 border-[var(--color-ink)] bg-[var(--color-canvas)] p-6 shadow-[6px_6px_0px_0px_rgba(18,20,23,1)] space-y-6">
              {/* Query Banner */}
              <div className="flex justify-between items-center border-b border-[var(--color-ink)] pb-3">
                <div className="space-y-0.5">
                  <div className="text-[10px] text-[var(--color-ink-tertiary)] uppercase font-bold">
                    ACTIVE LABORATORY INQUIRY:
                  </div>
                  <div className="text-base font-bold text-[var(--color-ink)]">
                    &gt; "{current.query}"
                  </div>
                </div>
                <span className="px-2 py-0.5 bg-[var(--color-ink)] text-white text-[10px] uppercase font-bold">
                  EVIDENCE TRACE
                </span>
              </div>

              {/* Execution Steps */}
              <div className="space-y-2">
                <div className="text-[10.5px] font-bold uppercase text-[var(--color-ink-tertiary)]">
                  MULTI-STAGE VERIFICATION PIPELINE:
                </div>
                <div className="space-y-1.5">
                  {current.steps.map((step, sIdx) => (
                    <div
                      key={sIdx}
                      className="p-2.5 bg-[var(--color-surface)] border border-[var(--color-ink)] flex items-start space-x-3 text-xs"
                    >
                      <span className="px-1.5 py-0.5 bg-[var(--color-surface-muted)] text-[10px] font-bold uppercase shrink-0">
                        {step.label}
                      </span>
                      <span className="text-[var(--color-ink)] leading-normal">{step.text}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Formulated Grounded Output */}
              <div className="p-4 bg-[var(--color-ink)] text-[#E8F1F5] text-xs leading-relaxed space-y-2 border border-[var(--color-ink)]">
                <div className="text-[var(--color-accent)] font-bold text-[10.5px] uppercase tracking-wider">
                  HALBERT GROUNDED FIRST-PERSON STATEMENT:
                </div>
                <div className="text-sm font-sans font-medium text-white leading-relaxed">
                  "{current.output}"
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
