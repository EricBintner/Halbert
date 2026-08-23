import React, { useState, useRef } from 'react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { AnimatedCLI } from './AnimatedCLI';
import { howAreYou } from '../lib/demo-scripts';
import { ArrowRight, CheckCircle2, ShieldCheck, HardDrive, Cpu, Terminal } from 'lucide-react';

gsap.registerPlugin(useGSAP, ScrollTrigger);

export function Hero({ waitlistRef }) {
  const container = useRef(null);
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState('idle'); // idle | submitting | success | error
  const [errorMessage, setErrorMessage] = useState('');

  useGSAP(() => {
    const mm = gsap.matchMedia();

    mm.add('(prefers-reduced-motion: no-preference)', () => {
      // Staggered entrance for hero text elements
      gsap.fromTo('.hero-reveal',
        { y: 24, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.7, stagger: 0.08, ease: 'power2.out', delay: 0.2 }
      );

      // Terminal demo glides in with a blur-to-sharp reveal
      gsap.fromTo('.hero-terminal',
        { y: 32, opacity: 0, filter: 'blur(8px)' },
        { y: 0, opacity: 1, filter: 'blur(0px)', duration: 0.9, ease: 'expo.out', delay: 0.4 }
      );
    });

    mm.add('(prefers-reduced-motion: reduce)', () => {
      gsap.set(['.hero-reveal', '.hero-terminal'], { opacity: 1, y: 0, clearProps: 'transform,filter' });
    });
  }, { scope: container });

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || !email.includes('@')) {
      setStatus('error');
      setErrorMessage('Please enter a valid email address.');
      return;
    }

    setStatus('submitting');
    try {
      const formData = new FormData(e.target);
      await fetch('/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams(formData).toString(),
      });
    } catch {
      // Netlify forms work even if fetch fails in dev — fall through to success
    }
    setStatus('success');
  };

  return (
    <section ref={container} className="relative min-h-[92svh] pt-28 pb-20 px-6 flex items-center justify-center paper-texture">
      <div className="max-w-[var(--content-max-width)] w-full mx-auto grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-8 items-center">
        {/* Left Column: Value Prop & Form */}
        <div className="lg:col-span-6 space-y-6 text-left">
          {/* Eyebrow badge */}
          <div className="hero-reveal inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-[var(--color-surface-subtle)] border border-[var(--color-hairline)] text-[12px] font-mono font-semibold tracking-wider uppercase text-[var(--color-ink-secondary)]">
            <span className="w-2 h-2 rounded-full bg-[var(--color-accent)] animate-pulse" />
            <span>Local-First Host Intelligence</span>
          </div>

          {/* Headline */}
          <h1 className="hero-reveal text-4xl sm:text-5xl lg:text-[54px] font-display font-semibold tracking-tight text-[var(--color-ink)] leading-[1.08]">
            Your computer has something to say<span className="text-[var(--color-accent)]">.</span>
          </h1>

          {/* Subhead */}
          <p className="hero-reveal text-lg sm:text-xl text-[var(--color-ink-secondary)] font-normal leading-relaxed max-w-xl">
            A local-first AI assistant that knows your machine — because it{' '}
            <em className="italic font-serif text-[var(--color-ink)]">is</em> your machine.
            Grounded in real telemetry, configuration history, and diagnostic truth.
          </p>

          {/* Tagline callout */}
          <div className="hero-reveal pt-1 pb-2">
            <p className="text-base font-display font-medium text-[var(--color-ink)] flex items-center space-x-2">
              <span className="text-[var(--color-accent)] font-bold">—</span>
              <span>"Halbert. You can call me AI."</span>
            </p>
          </div>

          {/* Early Access / Waitlist Form */}
          <div ref={waitlistRef} className="hero-reveal pt-2 max-w-md">
            {status === 'success' ? (
              <div className="p-4 rounded-xl bg-[#EEF6F2] border border-[#C2E0D1] flex items-center space-x-3 text-[#2D7A56]">
                <CheckCircle2 className="w-5 h-5 shrink-0" />
                <div className="text-sm font-medium">
                  You're on the early access list! We'll notify you when the preview build drops.
                </div>
              </div>
            ) : (
              <form
                name="waitlist"
                method="POST"
                data-netlify="true"
                onSubmit={handleSubmit}
                className="space-y-3"
              >
                <input type="hidden" name="form-name" value="waitlist" />
                <div className="flex flex-col sm:flex-row items-stretch gap-2.5">
                  <input
                    type="email"
                    name="email"
                    value={email}
                    onChange={(e) => {
                      setEmail(e.target.value);
                      if (status === 'error') setStatus('idle');
                    }}
                    placeholder="Enter your email address…"
                    className="flex-1 px-4 py-3 rounded-xl bg-[var(--color-surface)] border border-[var(--color-hairline-strong)] text-[var(--color-ink)] placeholder-[var(--color-ink-tertiary)] text-[15px] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] transition-all shadow-sm"
                    required
                  />
                  <button
                    type="submit"
                    disabled={status === 'submitting'}
                    className="px-6 py-3 rounded-xl bg-[var(--color-accent)] text-white text-[15px] font-semibold hover:bg-[var(--color-accent-hover)] transition-all shadow-md hover:shadow-[0_4px_16px_rgba(211,78,36,0.3)] active:translate-y-px shrink-0 flex items-center justify-center space-x-2"
                  >
                    <span>{status === 'submitting' ? 'Submitting…' : 'Join Waitlist'}</span>
                    <ArrowRight className="w-4 h-4" />
                  </button>
                </div>
                {status === 'error' && (
                  <p className="text-[13px] text-[var(--color-status-error)] font-medium">
                    {errorMessage}
                  </p>
                )}
              </form>
            )}

            {/* Platform pills */}
            <div className="pt-4 flex items-center space-x-4 text-[12px] font-mono text-[var(--color-ink-tertiary)]">
              <span className="flex items-center space-x-1">
                <ShieldCheck className="w-3.5 h-3.5 text-[var(--color-status-success)]" />
                <span>100% Local (Ollama)</span>
              </span>
              <span>•</span>
              <span>macOS &amp; Linux</span>
              <span>•</span>
              <span>Zero Cloud Telemetry</span>
            </div>
          </div>
        </div>

        {/* Right Column: Live Animated Conversation Terminal */}
        <div className="hero-terminal lg:col-span-6 w-full">
          <AnimatedCLI script={howAreYou} className="w-full min-h-[380px]" />
        </div>
      </div>
    </section>
  );
}
