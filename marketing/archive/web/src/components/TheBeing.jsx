import React from 'react';
import { AnimatedCLI } from './AnimatedCLI';
import { proactiveAlert } from '../lib/demo-scripts';

export function TheBeing({ copy }) {
  const soul = copy?.soul || {
    kicker: 'THE CENTRAL THESIS',
    headline: 'I am not an assistant.\nI am the machine.',
    body: [
      'When you ask a generic AI "How are you doing?", it tells you it is a language model without physical form.',
      'When you ask me, I tell you I’ve been up 42 days, my load is light, and my secondary drive needs attention.',
      'The most helpful colleague you have happens to be your computer.',
    ],
  };

  return (
    <section id="the-being" className="py-28 px-6 bg-[var(--color-canvas)] border-t-3 border-[var(--color-ink)] paper-texture">
      <div className="max-w-[var(--readable-max-width)] mx-auto space-y-16 text-left">
        {/* Kicker */}
        <div className="text-xs font-mono font-bold tracking-widest text-[var(--color-accent)] uppercase">
          {soul.kicker}
        </div>

        {/* Monumental Headline */}
        <h2 className="text-4xl sm:text-6xl lg:text-7xl font-display font-black tracking-tight text-[var(--color-ink)] leading-[1.02] whitespace-pre-line">
          {soul.headline}
        </h2>

        {/* Body Blocks */}
        <div className="space-y-6 text-lg sm:text-xl text-[var(--color-ink-secondary)] leading-relaxed max-w-2xl">
          {soul.body.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </div>

        {/* Proactive Alert Live Demonstrator */}
        <div className="pt-8 crop-marks">
          <div className="text-xs font-mono font-bold uppercase tracking-wider text-[var(--color-ink-tertiary)] mb-2">
            DEMONSTRATION: PROACTIVE MORNING TRIAGE LOG
          </div>
          <AnimatedCLI script={proactiveAlert} figure="FIG. B" className="w-full" />
        </div>
      </div>
    </section>
  );
}
