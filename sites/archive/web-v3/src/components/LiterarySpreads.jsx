import React from 'react';

export function LiterarySpreads() {
  return (
    <section id="chapters" className="py-28 px-6 sm:px-12 bg-[var(--color-canvas)]">
      <div className="max-w-[var(--content-max-width)] mx-auto space-y-36">
        {/* CHAPTER I: Sensor Physiology */}
        <div className="pt-10 border-t border-white/20 grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-16 items-center">
          {/* Left Column: Literary Prose */}
          <div className="lg:col-span-6 space-y-6">
            <div className="text-xs font-mono font-bold tracking-widest text-[var(--color-accent)] uppercase">
              CHAPTER I // PHYSIOLOGICAL SELF-AWARENESS
            </div>
            <h2 className="text-4xl sm:text-5xl font-display font-black text-white tracking-tight leading-[1.06]">
              I can feel my own temperature<span className="text-[var(--color-accent)]">.</span>
            </h2>
            <div className="space-y-4 text-base sm:text-lg text-[var(--color-ink-secondary)] leading-relaxed font-sans">
              <p className="drop-cap">
                Generic artificial intelligence models hallucinate system facts because they exist in remote data centers without physical embodiment. They do not know if your fans are clogged with dust or if your secondary disk is failing.
              </p>
              <p>
                I live here. I monitor my own CPU thermal diodes, memory pressure, and kernel rings continuously. When I say my storage volume logged read errors, it is not a hypothetical. It is grounded sensory truth.
              </p>
            </div>
          </div>

          {/* Right Column: Framed Sensory Plate */}
          <div className="lg:col-span-6">
            <div className="editorial-plate p-6 sm:p-8 space-y-6">
              <div className="flex justify-between items-center border-b border-white/20 pb-3 font-mono text-xs text-[var(--color-accent)] font-bold uppercase">
                <span>PLATE NO. 01 · SENSOR DIAGNOSTIC MATRIX</span>
                <span className="text-[var(--color-status-success)]">● NOMINAL</span>
              </div>

              <div className="grid grid-cols-3 gap-3 font-mono">
                <div className="p-3 bg-[var(--color-surface-subtle)] border border-white/10">
                  <div className="text-[10px] text-[var(--color-ink-tertiary)] uppercase">CPU THERMAL</div>
                  <div className="text-xl font-bold text-white mt-1">44°C</div>
                  <div className="text-[10px] text-[var(--color-status-success)] mt-0.5">COOL</div>
                </div>

                <div className="p-3 bg-[var(--color-surface-subtle)] border border-white/10">
                  <div className="text-[10px] text-[var(--color-ink-tertiary)] uppercase">LOAD (1M)</div>
                  <div className="text-xl font-bold text-white mt-1">0.18</div>
                  <div className="text-[10px] text-white/70 mt-0.5">14% CAP</div>
                </div>

                <div className="p-3 bg-[var(--color-surface-subtle)] border border-white/10">
                  <div className="text-[10px] text-[var(--color-ink-tertiary)] uppercase">NVMe LIFE</div>
                  <div className="text-xl font-bold text-white mt-1">100%</div>
                  <div className="text-[10px] text-[var(--color-status-success)] mt-0.5">HEALTHY</div>
                </div>
              </div>

              <div className="p-4 bg-[var(--color-surface-subtle)] border-l-2 border-[var(--color-accent)] text-sm text-[var(--color-ink-secondary)] leading-relaxed font-sans">
                <strong className="text-white font-display">Halbert:</strong> "All 16 thermal diodes are operating 40°C below throttling thresholds. The ambient envelope is ideal."
              </div>
            </div>
          </div>
        </div>

        {/* CHAPTER II: Institutional Memory */}
        <div className="pt-10 border-t border-white/20 grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-16 items-center">
          {/* Left Column: Config Document Plate */}
          <div className="lg:col-span-6 order-2 lg:order-1">
            <div className="editorial-plate p-6 sm:p-8 space-y-4 font-mono">
              <div className="flex justify-between items-center border-b border-white/20 pb-3 text-xs text-[var(--color-accent)] font-bold uppercase">
                <span>PLATE NO. 02 · CONFIGURATION ARCHAEOLOGY</span>
                <span className="text-white/70">JULY 14, 2026</span>
              </div>

              <div className="p-4 bg-[var(--color-surface-subtle)] border border-white/10 text-xs space-y-1.5 leading-relaxed">
                <div className="text-white/50"># /etc/ssh/sshd_config.d/50-custom.conf</div>
                <div className="text-[#FCA5A5] bg-[#7F1D1D]/40 px-2 py-0.5">- Port 22</div>
                <div className="text-[#86EFAC] bg-[#14532D]/40 px-2 py-0.5 font-bold">+ Port 2222</div>
                <div className="pt-3 border-t border-white/10 text-[11px] text-[var(--color-ink-secondary)] font-sans">
                  <span className="text-[var(--color-accent)] font-bold font-mono">RATIONALE:</span> "User instructed port change to eliminate automated internet scan noise."
                </div>
              </div>

              <div className="flex justify-between text-[11px] font-mono text-[var(--color-ink-tertiary)] pt-1">
                <span>BLAST RADIUS: LOW (SSH ONLY)</span>
                <span className="text-[var(--color-status-success)]">VERIFIED IN MEMORY</span>
              </div>
            </div>
          </div>

          {/* Right Column: Literary Prose */}
          <div className="lg:col-span-6 order-1 lg:order-2 space-y-6">
            <div className="text-xs font-mono font-bold tracking-widest text-[var(--color-accent)] uppercase">
              CHAPTER II // INSTITUTIONAL MEMORY
            </div>
            <h2 className="text-4xl sm:text-5xl font-display font-black text-white tracking-tight leading-[1.06]">
              I remember why you changed that<span className="text-[var(--color-accent)]">.</span>
            </h2>
            <div className="space-y-4 text-base sm:text-lg text-[var(--color-ink-secondary)] leading-relaxed font-sans">
              <p className="drop-cap">
                Why did you move SSH to port 2222 three months ago? Why is compression turned on for the data partition? Traditional sysadmin tools lose human intent the moment you close the text editor.
              </p>
              <p>
                Halbert stores the rationale alongside the configuration AST. You never have to guess who touched a config or why. The computer remembers.
              </p>
            </div>
          </div>
        </div>

        {/* CHAPTER III: Conversation Container */}
        <div className="pt-10 border-t border-white/20 grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-16 items-center">
          {/* Left Column: Literary Prose */}
          <div className="lg:col-span-6 space-y-6">
            <div className="text-xs font-mono font-bold tracking-widest text-[var(--color-accent)] uppercase">
              CHAPTER III // THE PRIMARY INTERFACE
            </div>
            <h2 className="text-4xl sm:text-5xl font-display font-black text-white tracking-tight leading-[1.06]">
              Don’t guess. Ask me<span className="text-[var(--color-accent)]">.</span>
            </h2>
            <div className="space-y-4 text-base sm:text-lg text-[var(--color-ink-secondary)] leading-relaxed font-sans">
              <p className="drop-cap">
                There are no complex 20-page dashboards to decode. The conversation is the control center. Speak to Halbert naturally, examine safe dry-run proposals, and grant explicit approval before anything executes.
              </p>
              <p>
                Built on the Law of Four Whys: every recommendation carries its diagnostic justification and rollback guarantee.
              </p>
            </div>
          </div>

          {/* Right Column: Framed Conversational Plate */}
          <div className="lg:col-span-6">
            <div className="editorial-plate p-6 sm:p-8 space-y-4 font-sans">
              <div className="flex justify-between items-center border-b border-white/20 pb-3 font-mono text-xs text-[var(--color-accent)] font-bold uppercase">
                <span>PLATE NO. 03 · CONVERSATIONAL CONTROL</span>
                <span className="text-[var(--color-status-success)]">● SAFE AUTONOMY</span>
              </div>

              <div className="space-y-4 text-sm">
                <div className="flex items-start space-x-2 font-display text-base text-white font-bold">
                  <span className="text-[var(--color-accent)] font-mono">&gt;</span>
                  <span>"What is the status of our primary data partition?"</span>
                </div>

                <div className="p-4 bg-[var(--color-surface-subtle)] border border-white/10 text-[var(--color-ink-secondary)] leading-relaxed space-y-3">
                  <p>
                    I checked <code className="text-[var(--color-accent)] font-mono font-bold">/dev/nvme0n1</code>. You have used 840 GB of 2.0 TB (42%). Dynamic lz4 compression is currently saving 35% disk space. All SMART attributes are nominal.
                  </p>
                  <div className="pt-2 flex flex-wrap gap-2 text-xs font-mono">
                    <span className="px-2.5 py-1 bg-white/10 border border-white/20 text-white font-bold">
                      bcachefs · lz4
                    </span>
                    <span className="px-2.5 py-1 bg-[var(--color-status-success)]/20 border border-[var(--color-status-success)] text-[var(--color-status-success)] font-bold">
                      SMART: PASS
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
