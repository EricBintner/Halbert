import React from 'react';

export function TypographicFeatures() {
  const sections = [
    {
      num: '01',
      id: 'features',
      headline: 'I can feel my own temperature.',
      sub: 'Generic artificial intelligence models are numb to physical reality. Halbert has sensors.',
      body: 'Generic models hallucinate system status because they live in remote data centers without physical hardware. Halbert runs on your host machine. It continuously monitors 16 thermal diodes, fan curves, memory pressure, and kernel rings. When it warns you that a secondary disk is logging timeouts, it is not a hypothetical. It is sensory fact.',
      badge: 'SENSORY INTAKE · /sys/class/hwmon',
    },
    {
      num: '02',
      id: 'memory',
      headline: 'I remember why you changed that.',
      sub: 'The human reason behind a configuration change is just as important as the syntax.',
      body: 'Why was SSH moved to port 2222 three months ago? Why is compression enabled on the data partition? Traditional sysadmin tools lose your intent the second you close the editor. Halbert preserves human rationale alongside configuration AST diffs. You will never have to guess why a daemon was modified.',
      badge: 'CONFIGURATION ARCHAEOLOGY',
    },
    {
      num: '03',
      id: 'manuals',
      headline: 'I know 16,000 pages of manuals by heart.',
      sub: 'Grounded technical truth without searching web forums or memorizing obscure flags.',
      body: 'Halbert embeds an indexed library of 16,000 technical manuals, system man pages, and kernel guides using local SourcePrep RAG. When you ask for complex multi-tool syntax, Halbert provides grounded citations and verifiable dry-run command proposals.',
      badge: 'SOURCEPREP LOCAL RAG',
    },
    {
      num: '04',
      id: 'privacy',
      headline: 'I never phone home.',
      sub: 'Your host telemetry and configurations never leave your physical machine.',
      body: 'Powered by Ollama with local neural weights. Zero telemetry egress. Every proposed action requires explicit human confirmation, backed by atomic dry-run previews and Polkit privilege isolation.',
      badge: '100% PRIVATE · ZERO CLOUD EGRESS',
    },
  ];

  return (
    <section className="py-24 px-6 sm:px-10 space-y-24 border-b border-white/25">
      <div className="max-w-[var(--content-max-width)] mx-auto space-y-24">
        {sections.map((sec, idx) => (
          <div
            key={sec.num}
            id={sec.id}
            className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-16 items-start pt-12 border-t border-white/25"
          >
            {/* Massive Retro Numeral */}
            <div className="lg:col-span-3">
              <div className="font-display font-black text-6xl sm:text-8xl text-[var(--color-accent-amber)] leading-none select-none">
                {sec.num}
              </div>
              <div className="mt-3 text-[11px] font-mono tracking-widest uppercase text-white/70">
                {sec.badge}
              </div>
            </div>

            {/* Headline & Body */}
            <div className="lg:col-span-9 space-y-5 text-left">
              <h2 className="text-3xl sm:text-5xl font-display font-black text-white tracking-tight leading-[1.06]">
                {sec.headline}
              </h2>
              <p className="text-xl retro-italic text-[var(--color-accent-amber)] font-normal leading-snug">
                "{sec.sub}"
              </p>
              <p className="text-base sm:text-lg text-[var(--color-ink-secondary)] leading-relaxed font-sans max-w-3xl">
                {sec.body}
              </p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
