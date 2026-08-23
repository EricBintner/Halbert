import React, { useRef } from 'react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { AnimatedCLI } from './AnimatedCLI';
import { proactiveAlert } from '../lib/demo-scripts';
import { Sparkles, Shield, HeartHandshake, Bot, Terminal } from 'lucide-react';

gsap.registerPlugin(useGSAP, ScrollTrigger);

export function TheBeing() {
  const container = useRef(null);

  useGSAP(() => {
    const mm = gsap.matchMedia();

    mm.add('(prefers-reduced-motion: no-preference)', () => {
      gsap.from('.being-reveal', {
        scrollTrigger: { trigger: container.current, start: 'top 75%' },
        y: 28,
        opacity: 0,
        duration: 0.8,
        stagger: 0.12,
        ease: 'power2.out',
      });
    });

    mm.add('(prefers-reduced-motion: reduce)', () => {
      gsap.set('.being-reveal', { opacity: 1, y: 0, clearProps: 'transform' });
    });
  }, { scope: container });

  return (
    <section ref={container} id="the-being" className="py-28 px-6 bg-[var(--color-canvas)] border-t border-[var(--color-hairline)] paper-texture">
      <div className="max-w-[var(--readable-max-width)] mx-auto text-center space-y-12">
        {/* Philosophy Badge */}
        <div className="being-reveal inline-flex items-center space-x-2 px-3.5 py-1 rounded-full bg-[var(--color-surface-subtle)] border border-[var(--color-hairline)] text-[12px] font-mono font-semibold uppercase tracking-wider text-[var(--color-ink-secondary)]">
          <Sparkles className="w-3.5 h-3.5 text-[var(--color-accent)]" />
          <span>The Philosophy of Embodiment</span>
        </div>

        {/* The Core Soul Statement */}
        <div className="being-reveal space-y-4">
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-display font-semibold tracking-tight text-[var(--color-ink)] leading-[1.12]">
            &ldquo;The most helpful colleague you have, who happens to be your computer.&rdquo;
          </h2>
          <p className="text-lg text-[var(--color-ink-secondary)] leading-relaxed max-w-xl mx-auto">
            Traditional AI assistants give you philosophical disclaimers about not having feelings.
            Halbert inverts the relationship: the model&rsquo;s identity <strong className="font-semibold text-[var(--color-ink)]">is</strong> the machine.
          </p>
        </div>

        {/* Morning Triage Live Demonstrator */}
        <div className="being-reveal pt-4 text-left">
          <AnimatedCLI script={proactiveAlert} className="w-full shadow-[var(--shadow-device)]" />
        </div>

        {/* 3 Core Philosophical Pillars */}
        <div className="being-reveal grid grid-cols-1 md:grid-cols-3 gap-6 text-left pt-6">
          <div className="p-5 rounded-2xl bg-[var(--color-surface)] border border-[var(--color-hairline)] space-y-2">
            <div className="font-display font-semibold text-[16px] text-[var(--color-ink)]">
              First-Person Voice
            </div>
            <p className="text-[13.5px] text-[var(--color-ink-secondary)] leading-relaxed">
              Never &ldquo;the host experienced an I/O fault.&rdquo; Always &ldquo;I logged three read errors on my secondary drive.&rdquo;
            </p>
          </div>

          <div className="p-5 rounded-2xl bg-[var(--color-surface)] border border-[var(--color-hairline)] space-y-2">
            <div className="font-display font-semibold text-[16px] text-[var(--color-ink)]">
              Zero Disclaimers
            </div>
            <p className="text-[13.5px] text-[var(--color-ink-secondary)] leading-relaxed">
              No generic chatbot hedging. When Halbert makes a recommendation, it is bound by live sensor verification.
            </p>
          </div>

          <div className="p-5 rounded-2xl bg-[var(--color-surface)] border border-[var(--color-hairline)] space-y-2">
            <div className="font-display font-semibold text-[16px] text-[var(--color-ink)]">
              Safe Autonomy
            </div>
            <p className="text-[13.5px] text-[var(--color-ink-secondary)] leading-relaxed">
              Every suggested system change provides an atomic diff, a blast-radius estimate, and an instant 1-click rollback.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
