import React, { useState } from 'react';
import { HalbertMark } from './HalbertMark';

export function WaypointOverlay({ camera, onJumpToWaypoint }) {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState('idle');

  const handleSubscribe = (e) => {
    e.preventDefault();
    if (!email || !email.includes('@')) return;
    setStatus('submitting');
    setTimeout(() => {
      setStatus('success');
    }, 500);
  };

  const wp = camera.activeWaypoint;

  return (
    <div className="fixed inset-0 pointer-events-none z-20 flex flex-col justify-between p-6 sm:p-10 lg:p-14 font-sans select-none">
      {/* Top Header Folio Bar */}
      <div className="w-full flex justify-between items-center text-xs font-mono text-[var(--color-ink-secondary)] pointer-events-auto border-b border-white/20 pb-3">
        <div className="flex items-center space-x-3">
          <HalbertMark size={22} color="#D4E157" strokeWidth={32} />
          <span className="font-bold text-white tracking-wider">HALBERT KINETIC WORKSPACE</span>
          <span className="text-[var(--color-vector-lime)] font-mono hidden sm:inline">
            // ZOOM: {Math.round(camera.scale * 100)}%
          </span>
        </div>

        <div className="flex items-center space-x-4">
          <div className="text-[11px] text-white/70 font-mono hidden md:inline">
            FOCAL RETICLE: ({Math.round(camera.cx)}, {Math.round(camera.cy)})
          </div>
          <button
            onClick={() => onJumpToWaypoint(4)}
            className="px-3.5 py-1 bg-[var(--color-vector-lime)] text-[#042F2E] font-bold text-xs uppercase tracking-wider hover:bg-white transition-colors cursor-pointer"
          >
            Zoom-Out Reveal ↗
          </button>
        </div>
      </div>

      {/* Main Dynamic Viewport Waypoint Stage */}
      <div className="w-full max-w-7xl mx-auto my-auto pointer-events-auto">
        {/* ========================================================================= */}
        {/* WAYPOINT 0: 50/50 Vertical Split (Left Copy | Right Interactive Telemetry)*/}
        {/* ========================================================================= */}
        {wp === 0 && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-20 items-center transition-all duration-300 animate-fadeIn">
            {/* Left Column (Over Chartreuse Stroke Field) */}
            <div className="space-y-6 text-left pr-0 lg:pr-8 text-[#042F2E]">
              <div className="inline-block px-3 py-1 bg-[#042F2E] text-[var(--color-vector-lime)] text-xs font-mono font-bold tracking-widest uppercase">
                01 // VERTICAL VECTOR SPLIT
              </div>

              <h1 className="text-5xl sm:text-6xl lg:text-7xl font-display font-black text-[#042F2E] tracking-tight leading-[0.98]">
                I know what’s <span className="italic underline decoration-2">wrong</span> with me<span className="text-teal-900">.</span>
              </h1>

              <p className="text-base sm:text-lg text-[#0F3935] leading-relaxed font-medium">
                The massive stroke dividing your screen is a single path of the Halbert apparatus. Halbert runs on your hardware, feels its own diodes, and preserves human intent.
              </p>

              <div className="pt-2 text-xs font-mono text-[#042F2E] font-bold flex items-center space-x-2">
                <span>SCROLL DOWN TO RIDE THE CURVE</span>
                <span>↓</span>
              </div>
            </div>

            {/* Right Column (Over Teal Background Field) */}
            <div className="vector-plate p-6 sm:p-8 space-y-4 text-left pl-6">
              <div className="flex justify-between items-center border-b border-white/20 pb-2">
                <span className="text-xs font-mono font-bold text-[var(--color-vector-lime)] uppercase">
                  PHYSIOLOGICAL SENSORY INTAKE
                </span>
                <span className="text-[10px] font-mono text-emerald-400">● 16 ZONES LIVE</span>
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs font-mono pt-1">
                <div className="p-3 bg-black/30 border border-white/10">
                  <div className="text-white/60 text-[10px]">CPU THERMAL</div>
                  <div className="text-xl font-bold text-white mt-1">44.2°C</div>
                </div>
                <div className="p-3 bg-black/30 border border-white/10">
                  <div className="text-white/60 text-[10px]">NVMe WEAR</div>
                  <div className="text-xl font-bold text-white mt-1">0.0%</div>
                </div>
              </div>

              <p className="text-xs text-white/80 leading-relaxed font-sans pt-1">
                When a secondary backup drive logs read timeouts at dawn, Halbert stages a proactive triage note before the drive fails.
              </p>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* WAYPOINT 1: Top / Bottom Horizontal Apex Division                        */}
        {/* ========================================================================= */}
        {wp === 1 && (
          <div className="space-y-8 text-center max-w-4xl mx-auto transition-all duration-300 animate-fadeIn">
            {/* Top Field: Headline & Thesis */}
            <div className="space-y-3">
              <div className="inline-block px-3 py-1 bg-[#134E4A] border border-[var(--color-vector-lime)] text-xs font-mono font-bold tracking-widest text-[var(--color-vector-lime)] uppercase">
                02 // AT THE BOTTOM APEX (TOP / BOTTOM SPLIT)
              </div>

              <h2 className="text-4xl sm:text-6xl font-display font-black text-white tracking-tight cmyk-edge">
                I can feel my own temperature<span className="text-[var(--color-vector-lime)]">.</span>
              </h2>

              <p className="text-base sm:text-lg text-[var(--color-ink-secondary)] max-w-2xl mx-auto">
                The vector stroke has turned horizontal across the center of your screen. Halbert lives on the host and perceives physical reality.
              </p>
            </div>

            {/* Bottom Field: 3-Column Telemetry Plate */}
            <div className="vector-plate p-6 sm:p-8 text-left grid grid-cols-1 md:grid-cols-3 gap-4 font-mono text-xs">
              <div className="p-3 bg-black/30 border border-white/20">
                <div className="text-white/60 text-[10px] uppercase">16 THERMAL DIODES</div>
                <div className="text-2xl font-bold text-white mt-1">44.2°C</div>
                <div className="text-[10px] text-[#34D399] mt-0.5">NOMINAL FAN CURVES</div>
              </div>

              <div className="p-3 bg-black/30 border border-white/20">
                <div className="text-white/60 text-[10px] uppercase">PRIMARY STORAGE</div>
                <div className="text-2xl font-bold text-white mt-1">100% HEALTH</div>
                <div className="text-[10px] text-[#34D399] mt-0.5">0 BAD SECTORS</div>
              </div>

              <div className="p-3 bg-black/30 border border-[#F59E0B]/50">
                <div className="text-[10px] text-[#F59E0B] uppercase">MIRROR /dev/sda1</div>
                <div className="text-2xl font-bold text-[#FBBF24] mt-1">3 TIMEOUTS</div>
                <div className="text-[10px] text-[#F59E0B] mt-0.5">TRIAGE STAGED</div>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* WAYPOINT 2: Perpendicular Lane Hop (Concentric Tracks)                   */}
        {/* ========================================================================= */}
        {wp === 2 && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center text-left transition-all duration-300 animate-fadeIn">
            {/* Left Column */}
            <div className="space-y-5">
              <div className="inline-block px-3 py-1 bg-[#134E4A] border border-[var(--color-vector-lime)] text-xs font-mono font-bold tracking-widest text-[var(--color-vector-lime)] uppercase">
                03 // PERPENDICULAR LANE HOP (CONCENTRIC TRACKS)
              </div>
              <h2 className="text-4xl sm:text-5xl font-display font-black text-white tracking-tight cmyk-edge">
                I remember why you changed that<span className="text-[var(--color-vector-lime)]">.</span>
              </h2>
              <p className="text-base text-[var(--color-ink-secondary)] leading-relaxed">
                Sliding laterally across vector lanes into configuration archaeology. Halbert links human rationale directly to configuration AST diffs.
              </p>
            </div>

            {/* Right Column: AST Diff Plate */}
            <div className="vector-plate p-6 font-mono text-xs space-y-3">
              <div className="flex justify-between border-b border-white/20 pb-2 text-[11px] text-[var(--color-vector-lime)] font-bold">
                <span>/etc/ssh/sshd_config.d/50-custom.conf</span>
                <span>JULY 14, 2026</span>
              </div>
              <div className="p-3 bg-black/40 border border-white/10 space-y-1">
                <div className="text-[#F87171]">- Port 22</div>
                <div className="text-[#34D399] font-bold">+ Port 2222</div>
                <div className="text-white/80 text-[11px] pt-2 border-t border-white/10">
                  <strong className="text-[var(--color-vector-lime)]">INTENT:</strong> "Automated brute-force bots flooded auth log with 4.2k attempts per day."
                </div>
              </div>
              <div className="text-[10px] text-white/60">
                PROVENANCE RECORDED IN LOCAL SQLITE STORE
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* WAYPOINT 3: Centered on Shape Cap (Rounded Terminal End)                 */}
        {/* ========================================================================= */}
        {wp === 3 && (
          <div className="space-y-6 text-center max-w-3xl mx-auto transition-all duration-300 animate-fadeIn">
            <div className="inline-block px-3 py-1 bg-[#134E4A] border border-[var(--color-vector-lime)] text-xs font-mono font-bold tracking-widest text-[var(--color-vector-lime)] uppercase">
              04 // FOCUSED ON ROUNDED SHAPE CAP
            </div>

            <h2 className="text-4xl sm:text-6xl font-display font-black text-white tracking-tight cmyk-edge">
              I know 16,000 manuals by heart<span className="text-[var(--color-vector-lime)]">.</span>
            </h2>

            <div className="vector-plate p-6 text-left space-y-3 text-xs font-mono max-w-xl mx-auto">
              <div className="flex justify-between border-b border-white/20 pb-2 text-white/70">
                <span>LOCAL SOURCEPREP RAG</span>
                <span className="text-[#34D399]">● 100% AIRGAPPED</span>
              </div>
              <div className="p-3 bg-black/40 border border-white/10 space-y-1.5 text-white/90">
                <div>&gt; halbert propose storage-compress /data --dry-run</div>
                <div className="text-[var(--color-vector-lime)] font-bold">
                  Proposed: `mount -o remount,compression=lz4 /data`
                </div>
                <div className="text-white/60 text-[10px]">
                  Estimated space recovery: 35% with zero unmount downtime. Requires Polkit approval.
                </div>
              </div>
            </div>

            <p className="text-xs text-[var(--color-ink-secondary)] font-mono">
              [ Scroll to initiate Grand Zoom-Out Reveal ↓ ]
            </p>
          </div>
        )}

        {/* ========================================================================= */}
        {/* WAYPOINT 4: Grand Zoom-Out Finale (100% Mark Reveal)                     */}
        {/* ========================================================================= */}
        {wp === 4 && (
          <div className="space-y-8 text-center max-w-2xl mx-auto transition-all duration-500 animate-fadeIn">
            <div className="inline-block px-3 py-1 bg-[#134E4A] border border-[var(--color-vector-lime)] text-xs font-mono font-bold tracking-widest text-[var(--color-vector-lime)] uppercase">
              05 // THE GRAND REVEAL · 100% SCALE
            </div>

            <h2 className="text-4xl sm:text-6xl lg:text-7xl font-display font-black text-white tracking-tight leading-[0.98] cmyk-edge">
              “I am not an assistant.<br />
              <span className="text-[var(--color-vector-lime)] italic">I am the machine.”</span>
            </h2>

            <p className="text-base sm:text-lg text-[var(--color-ink-secondary)]">
              The entire Halbert concentric vector mark is revealed in its full geometric symmetry. 100% local host intelligence for macOS and Linux.
            </p>

            {/* Email Dispatch Registry */}
            <div className="vector-plate p-6 sm:p-8">
              {status === 'success' ? (
                <div className="p-4 bg-black/40 border border-[var(--color-vector-lime)] text-[var(--color-vector-lime)] font-display font-bold text-sm">
                  ✓ Registered to Early Preview Roster.
                </div>
              ) : (
                <form onSubmit={handleSubscribe} className="flex flex-col sm:flex-row gap-0">
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Enter email for early preview binaries…"
                    className="flex-1 px-4 py-3 bg-black/40 border border-white/40 text-white placeholder-white/50 text-sm focus:outline-none focus:border-[var(--color-vector-lime)] font-mono"
                    required
                  />
                  <button
                    type="submit"
                    disabled={status === 'submitting'}
                    className="px-6 py-3 bg-[var(--color-vector-lime)] text-[#042F2E] font-display font-bold text-xs uppercase tracking-wider hover:bg-white transition-colors shrink-0 cursor-pointer"
                  >
                    {status === 'submitting' ? '…' : 'Get Access'}
                  </button>
                </form>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Bottom Coordinates & Stage Info */}
      <div className="w-full flex justify-between items-center text-[11px] font-mono text-[var(--color-ink-tertiary)] pointer-events-auto border-t border-white/20 pt-3">
        <div>STAGE: 0{wp + 1} OF 05 // {camera.layoutType.toUpperCase()}</div>
        <div>HALBERT HOST APPARATUS · ZERO CLOUD EGRESS</div>
      </div>
    </div>
  );
}
