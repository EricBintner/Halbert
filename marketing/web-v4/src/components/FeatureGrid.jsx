import React from 'react';
import { Activity, Clock, BookOpen, ShieldCheck } from 'lucide-react';

export function FeatureGrid() {
  const features = [
    {
      icon: Activity,
      iconColor: 'text-[#2563EB] bg-[#EFF6FF] border-[#BFDBFE]',
      headline: 'I catch issues before they break.',
      description:
        'Continuous local intake across sensor telemetry, journald logs, and memory pressure. If a drive degrades, I stage a diagnostic report with zero guesswork.',
      meta: 'Proactive Sensory Triage',
    },
    {
      icon: Clock,
      iconColor: 'text-[#D97706] bg-[#FFFBEB] border-[#FDE68A]',
      headline: 'I remember why you changed that setting.',
      description:
        'Every configuration edit is tracked alongside your human rationale. Never wonder why a port was moved or a flag was added six months ago.',
      meta: 'Institutional Memory',
    },
    {
      icon: BookOpen,
      iconColor: 'text-[#7C3AED] bg-[#F5F3FF] border-[#DDD6FE]',
      headline: 'I know 16,000 pages of manuals by heart.',
      description:
        'Instant grounded answers for Linux, macOS, and BSD tools without searching web forums or memorizing obscure flags.',
      meta: 'SourcePrep Documentation RAG',
    },
    {
      icon: ShieldCheck,
      iconColor: 'text-[#10B981] bg-[#ECFDF5] border-[#A7F3D0]',
      headline: 'I run 100% locally on your machine.',
      description:
        'Powered by Ollama. Zero telemetry leaves your computer. Atomic dry-runs and explicit user approval before modifying any system file.',
      meta: 'Polkit Privilege Isolation',
    },
  ];

  return (
    <section id="features" className="py-24 px-6 bg-[var(--color-canvas)] border-b border-[var(--color-surface-muted)]">
      <div className="max-w-[var(--content-max-width)] mx-auto space-y-16">
        {/* Section Header */}
        <div className="max-w-2xl text-left space-y-3">
          <div className="text-xs font-mono font-semibold uppercase tracking-widest text-[var(--color-brand-blue)]">
            Core Capabilities
          </div>
          <h2 className="text-3xl sm:text-4xl font-display font-extrabold text-[var(--color-ink)] tracking-tight">
            Built for power users who value speed and clarity.
          </h2>
          <p className="text-base text-[var(--color-ink-secondary)] font-normal">
            No bloated dashboards or cloud dependencies. Just an intelligent, responsive host that knows your machine inside out.
          </p>
        </div>

        {/* 2x2 Clean Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          {features.map((f, idx) => {
            const Icon = f.icon;
            return (
              <div
                key={idx}
                className="minimal-card p-8 rounded-2xl space-y-5 hover:border-[var(--color-ink-ghost)] transition-all"
              >
                <div className="flex items-center justify-between">
                  <div className={`w-12 h-12 rounded-xl flex items-center justify-center border ${f.iconColor}`}>
                    <Icon size={22} />
                  </div>
                  <span className="text-[11px] font-mono text-[var(--color-ink-tertiary)] uppercase font-medium">
                    {f.meta}
                  </span>
                </div>

                <div className="space-y-2">
                  <h3 className="text-xl font-display font-bold text-[var(--color-ink)] leading-snug">
                    {f.headline}
                  </h3>
                  <p className="text-sm text-[var(--color-ink-secondary)] leading-relaxed font-sans">
                    {f.description}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
