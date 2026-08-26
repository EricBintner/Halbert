import React, { useState } from 'react';
import { AnimatedCLI } from './AnimatedCLI';
import { howAreYou } from '../lib/demo-scripts';

export function Hero({ copy, waitlistRef }) {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState('idle');

  const heroCopy = copy?.hero || {
    headline: 'I know what’s wrong with me.',
    bodyBlocks: [
      'I read my own hardware sensors, system logs, and configuration history.',
      'When something breaks, I don’t give you a dashboard to decode. I tell you — in plain language, with evidence.',
      'No cloud. No disclaimers. I run locally on your machine because I am your machine.',
    ],
    tagline: 'Halbert. You can call me AI.',
    formPlaceholder: 'Enter your email for early access…',
    submitText: 'Subscribe',
    successMessage: 'You are on the list. We will dispatch the build to your inbox.',
    badges: ['100% LOCAL (OLLAMA)', 'MACOS & LINUX', 'ZERO CLOUD TELEMETRY'],
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!email || !email.includes('@')) return;
    setStatus('submitting');
    setTimeout(() => {
      setStatus('success');
    }, 500);
  };

  return (
    <section className="relative pt-16 pb-24 px-6 paper-texture border-b-3 border-[var(--color-ink)]">
      <div className="max-w-[var(--content-max-width)] mx-auto grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-16 items-start">
        {/* Left Column: Asymmetric DDB Print Layout */}
        <div className="lg:col-span-6 space-y-8 text-left">
          {/* Main Statement Headline */}
          <h1 className="text-5xl sm:text-6xl lg:text-[68px] font-display font-extrabold tracking-tight text-[var(--color-ink)] leading-[1.02]">
            {heroCopy.headline}
          </h1>

          {/* Telegraphic Body Blocks */}
          <div className="space-y-4 text-base sm:text-lg text-[var(--color-ink-secondary)] font-normal leading-relaxed max-w-lg">
            {heroCopy.bodyBlocks.map((block, idx) => (
              <p key={idx}>{block}</p>
            ))}
          </div>

          {/* Tagline Callout */}
          <div className="pt-2 pb-2 border-l-3 border-[var(--color-accent)] pl-4">
            <p className="font-display font-bold text-lg text-[var(--color-ink)] tracking-tight">
              {heroCopy.tagline}
            </p>
          </div>

          {/* Subscription / Waitlist Form */}
          <div ref={waitlistRef} className="pt-4 max-w-md">
            {status === 'success' ? (
              <div className="p-4 bg-[var(--color-ink)] text-white font-mono text-sm border-2 border-[var(--color-ink)] shadow-[4px_4px_0px_0px_rgba(211,78,36,1)]">
                ✓ {heroCopy.successMessage}
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
                <div className="flex flex-col sm:flex-row items-stretch gap-0">
                  <input
                    type="email"
                    name="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder={heroCopy.formPlaceholder}
                    className="flex-1 px-4 py-3.5 bg-[var(--color-surface)] border-2 border-[var(--color-ink)] text-[var(--color-ink)] placeholder-[var(--color-ink-tertiary)] font-mono text-sm focus:outline-none focus:bg-[var(--color-surface-subtle)]"
                    required
                  />
                  <button
                    type="submit"
                    disabled={status === 'submitting'}
                    className="px-6 py-3.5 bg-[var(--color-accent)] text-white border-2 border-[var(--color-ink)] sm:border-l-0 font-display font-bold text-sm tracking-wider uppercase hover:bg-[var(--color-accent-hover)] transition-colors shadow-[4px_4px_0px_0px_rgba(26,25,24,1)] active:translate-y-0.5"
                  >
                    {status === 'submitting' ? '…' : heroCopy.submitText}
                  </button>
                </div>
              </form>
            )}

            {/* Badges / Commitments */}
            <div className="pt-6 flex flex-wrap gap-4 text-[11px] font-mono font-bold tracking-wider text-[var(--color-ink-tertiary)]">
              {heroCopy.badges.map((badge, idx) => (
                <span key={idx} className="flex items-center">
                  <span className="w-1.5 h-1.5 bg-[var(--color-ink)] mr-1.5" />
                  {badge}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Right Column: Sharp Animated Terminal Demo with Crop Marks */}
        <div className="lg:col-span-6 w-full crop-marks pt-2">
          <AnimatedCLI script={howAreYou} figure="FIG. A" className="w-full min-h-[380px]" />
          <div className="pt-3 flex justify-between items-center text-[11px] font-mono text-[var(--color-ink-tertiary)] uppercase tracking-wider">
            <span>UNALTERED SENSOR RECORDING</span>
            <span>HOST: UBUNTU-SERVER-01</span>
          </div>
        </div>
      </div>
    </section>
  );
}
