import React, { useState, useRef } from 'react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { DesktopWindow } from './DesktopWindow';
import { Cpu, HardDrive, FileText, CheckCircle, AlertTriangle, ArrowRight, ShieldCheck, Activity } from 'lucide-react';

gsap.registerPlugin(useGSAP, ScrollTrigger);

export function HowItWorks() {
  const container = useRef(null);
  const [activeStep, setActiveStep] = useState(0);

  const steps = [
    {
      id: 'knows-itself',
      tab: 'vitals',
      number: '01',
      title: 'It knows itself.',
      subtitle: 'System state as living physiology.',
      description:
        'Generic LLMs hallucinate system facts. Halbert reads live sensors, mount points, and journald logs directly through its local sensor loop. When it speaks about memory pressure or thermal stress, it quotes grounded reality.',
    },
    {
      id: 'remembers',
      tab: 'config',
      number: '02',
      title: 'It remembers.',
      subtitle: 'Configuration history and past rationale.',
      description:
        'Why is SSH on port 2222? Who enabled compression on the backup volume? Halbert tracks configuration modifications alongside user rationale. When you ask about system state, it answers with institutional memory.',
    },
    {
      id: 'speaks',
      tab: 'storage',
      number: '03',
      title: 'It speaks.',
      subtitle: 'Conversation as the primary container.',
      description:
        'No 17-page complex dashboards to navigate. The conversation is the control center. Ask questions naturally, approve safe dry-runs, and summon diagnostic proof modules dynamically into the workspace.',
    },
  ];

  useGSAP(() => {
    const mm = gsap.matchMedia();

    mm.add('(min-width: 1024px) and (prefers-reduced-motion: no-preference)', () => {
      // Scroll-driven step activation: each step card triggers activeStep change
      const stepEls = gsap.utils.toArray('.step-card');
      stepEls.forEach((el, i) => {
        ScrollTrigger.create({
          trigger: el,
          start: 'top 50%',
          end: 'bottom 50%',
          onToggle: (self) => {
            if (self.isActive) setActiveStep(i);
          },
          onLeaveBack: () => {
            if (i === 0) setActiveStep(0);
          },
        });
      });

      // Fade in section header on scroll
      gsap.from('.howitworks-header', {
        scrollTrigger: { trigger: '.howitworks-header', start: 'top 80%' },
        y: 24,
        opacity: 0,
        duration: 0.7,
        ease: 'power2.out',
      });
    });

    mm.add('(prefers-reduced-motion: reduce)', () => {
      gsap.set(['.howitworks-header', '.step-card'], { opacity: 1, y: 0, clearProps: 'transform' });
    });
  }, { scope: container });

  return (
    <section ref={container} id="how-it-works" className="py-24 px-6 border-t border-[var(--color-hairline)] bg-[var(--color-canvas)]">
      <div className="max-w-[var(--content-max-width)] mx-auto space-y-16">
        {/* Section Header */}
        <div className="howitworks-header text-center max-w-2xl mx-auto space-y-3">
          <div className="text-[12px] font-mono font-semibold uppercase tracking-widest text-[var(--color-accent)]">
            How It Works
          </div>
          <h2 className="text-3xl sm:text-4xl font-display font-semibold text-[var(--color-ink)]">
            The computer as your most helpful colleague<span className="text-[var(--color-accent)]">.</span>
          </h2>
          <p className="text-[16px] text-[var(--color-ink-secondary)] leading-relaxed">
            Built on the Law of Four Whys: every recommendation is grounded in real telemetry, past rationale, and verifiable proof.
          </p>
        </div>

        {/* 2-Column Scrollytelling Stage */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-start">
          {/* Left Column: Scroll-Driven Step Cards */}
          <div className="lg:col-span-5 space-y-4">
            {steps.map((step, idx) => {
              const isSelected = activeStep === idx;
              return (
                <div
                  key={step.id}
                  className={`step-card p-6 rounded-2xl border transition-all duration-500 cursor-pointer ${
                    isSelected
                      ? 'bg-[var(--color-surface)] border-[var(--color-accent)] shadow-[var(--shadow-card)] ring-1 ring-[var(--color-accent)]/20'
                      : 'bg-[var(--color-surface)]/50 border-[var(--color-hairline)] hover:bg-[var(--color-surface)] hover:border-[var(--color-hairline-strong)]'
                  }`}
                  onClick={() => setActiveStep(idx)}
                >
                  <div className="flex items-center space-x-3 text-xs font-mono font-bold mb-2">
                    <span
                      className={`px-2 py-0.5 rounded ${
                        isSelected
                          ? 'bg-[var(--color-accent)] text-white'
                          : 'bg-[var(--color-surface-muted)] text-[var(--color-ink-secondary)]'
                      }`}
                    >
                      {step.number}
                    </span>
                    <span className="text-[var(--color-ink-tertiary)] uppercase tracking-wider">
                      {step.subtitle}
                    </span>
                  </div>
                  <h3 className="text-xl font-display font-semibold text-[var(--color-ink)] mb-2">
                    {step.title}
                  </h3>
                  <p className="text-[14.5px] text-[var(--color-ink-secondary)] leading-relaxed">
                    {step.description}
                  </p>
                </div>
              );
            })}
          </div>

          {/* Right Column: Sticky Dynamic Desktop Window Mockup */}
          <div className="lg:col-span-7 lg:sticky lg:top-24">
            <DesktopWindow activeTab={steps[activeStep].tab} title={`Halbert — ${steps[activeStep].title}`}>
              {/* Step 1 Mockup: Vitals Matrix */}
              {activeStep === 0 && (
                <div className="space-y-6">
                  <div className="flex items-center justify-between pb-4 border-b border-[var(--color-hairline)]">
                    <div className="flex items-center space-x-2.5">
                      <Cpu className="w-5 h-5 text-[var(--color-accent)]" />
                      <span className="font-mono text-sm font-semibold text-[var(--color-ink)]">
                        System Vitals &amp; Sensor Telemetry
                      </span>
                    </div>
                    <span className="text-[12px] font-mono text-[var(--color-status-success)] bg-[#EEF6F2] px-2 py-0.5 rounded border border-[#C2E0D1]">
                      ● Sensors Nominal
                    </span>
                  </div>

                  <div className="grid grid-cols-3 gap-4">
                    <div className="p-4 rounded-xl bg-[var(--color-surface-subtle)] border border-[var(--color-hairline)]">
                      <div className="text-[12px] font-mono text-[var(--color-ink-secondary)]">CPU Temperature</div>
                      <div className="text-2xl font-mono font-bold text-[var(--color-ink)] mt-1">45°C</div>
                      <div className="text-[11px] font-mono text-[var(--color-status-success)] mt-1">Cool &amp; Quiet</div>
                    </div>
                    <div className="p-4 rounded-xl bg-[var(--color-surface-subtle)] border border-[var(--color-hairline)]">
                      <div className="text-[12px] font-mono text-[var(--color-ink-secondary)]">Load Average</div>
                      <div className="text-2xl font-mono font-bold text-[var(--color-ink)] mt-1">0.15</div>
                      <div className="text-[11px] font-mono text-[var(--color-status-success)] mt-1">12% capacity</div>
                    </div>
                    <div className="p-4 rounded-xl bg-[var(--color-surface-subtle)] border border-[var(--color-hairline)]">
                      <div className="text-[12px] font-mono text-[var(--color-ink-secondary)]">NVMe Health</div>
                      <div className="text-2xl font-mono font-bold text-[var(--color-ink)] mt-1">100%</div>
                      <div className="text-[11px] font-mono text-[var(--color-status-success)] mt-1">0 bad blocks</div>
                    </div>
                  </div>

                  <div className="p-3.5 rounded-xl bg-[#F0F6F9] border border-[#BFD8E6] text-[13px] font-mono text-[#386C8A] flex items-center space-x-2">
                    <Activity className="w-4 h-4 shrink-0" />
                    <span>Halbert: "I feel great. All thermal zones are well below throttling thresholds."</span>
                  </div>
                </div>
              )}

              {/* Step 2 Mockup: Config Diff Inspector */}
              {activeStep === 1 && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between pb-3 border-b border-[var(--color-hairline)]">
                    <div className="flex items-center space-x-2">
                      <FileText className="w-4 h-4 text-[var(--color-accent)]" />
                      <span className="font-mono text-sm font-semibold text-[var(--color-ink)]">
                        /etc/ssh/sshd_config.d/50-custom.conf
                      </span>
                    </div>
                    <span className="text-xs font-mono text-[var(--color-ink-tertiary)]">July 14, 2026</span>
                  </div>

                  <div className="p-4 rounded-xl bg-[var(--color-surface-subtle)] border border-[var(--color-hairline)] font-mono text-[13px] space-y-1.5">
                    <div className="text-[var(--color-ink-tertiary)]"># SSH Port Hardening</div>
                    <div className="text-[#C83E2D] bg-[#FDF2F0] px-2 py-0.5 rounded">- Port 22</div>
                    <div className="text-[#2D7A56] bg-[#EEF6F2] px-2 py-0.5 rounded">+ Port 2222</div>
                    <div className="text-[var(--color-ink-secondary)] pt-2 text-xs border-t border-[var(--color-hairline)]">
                      <span className="font-semibold text-[var(--color-accent)]">Why So:</span> "User instructed port change to eliminate automated bruteforce noise."
                    </div>
                  </div>

                  <div className="flex items-center justify-between text-xs font-mono text-[var(--color-ink-secondary)] pt-2">
                    <span>Blast Radius: Low (Incoming SSH only)</span>
                    <span className="text-[var(--color-status-success)] font-medium">Verified in Memory</span>
                  </div>
                </div>
              )}

              {/* Step 3 Mockup: Conversational Spine */}
              {activeStep === 2 && (
                <div className="space-y-4 font-mono text-[13.5px]">
                  {/* User bubble */}
                  <div className="flex items-start space-x-2">
                    <span className="text-[var(--color-accent)] font-bold">&gt;</span>
                    <div className="font-semibold text-[var(--color-ink)]">
                      What's the status of our data volume?
                    </div>
                  </div>

                  {/* Agent Response */}
                  <div className="p-4 rounded-xl bg-[var(--color-surface-subtle)] border border-[var(--color-hairline)] text-[var(--color-ink)] leading-relaxed space-y-3">
                    <p>
                      I checked <code className="text-[var(--color-accent)]">/dev/nvme0n1</code>. You've used 840 GB of 2.0 TB (42%). Compression is currently saving 35% disk space. All SMART attributes are nominal.
                    </p>
                    <div className="pt-2 flex items-center space-x-2 text-xs">
                      <span className="px-2.5 py-1 rounded bg-[var(--color-surface)] border border-[var(--color-hairline)] font-medium">
                        bcachefs · lz4 compression
                      </span>
                      <span className="text-[var(--color-status-success)] flex items-center">
                        <CheckCircle className="w-3.5 h-3.5 mr-1" />
                        Healthy
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </DesktopWindow>
          </div>
        </div>
      </div>
    </section>
  );
}
