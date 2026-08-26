import React from 'react';

export function QuoteSection() {
  return (
    <section className="py-28 px-6 sm:px-10 bg-[#1E3A8A] border-b border-white/25 text-left">
      <div className="max-w-[var(--readable-max-width)] mx-auto space-y-8">
        <div className="text-xs font-mono font-bold tracking-widest text-[var(--color-accent-amber)] uppercase">
          THE PHILOSOPHY OF EMBODIMENT
        </div>

        <blockquote className="text-4xl sm:text-6xl lg:text-7xl font-display font-black text-white leading-[1.04] tracking-tight">
          “I am not an assistant in the cloud.<br />
          <span className="retro-italic font-normal text-[var(--color-accent-amber)]">
            I am the machine sitting in front of you.”
          </span>
        </blockquote>

        <p className="text-lg sm:text-xl text-[var(--color-ink-secondary)] leading-relaxed font-sans max-w-2xl">
          When you ask a cloud chatbot how it's doing, it offers disclaimers about not possessing a body. When you ask Halbert, it tells you its load is light, its fan curves are quiet, and its secondary backup drive needs attention.
        </p>
      </div>
    </section>
  );
}
