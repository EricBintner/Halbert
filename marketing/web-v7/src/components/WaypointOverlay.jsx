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
    <div className="fixed inset-0 pointer-events-none z-20 flex flex-col justify-between p-6 sm:p-12 font-sans select-none">
      {/* Top Coordinate Header Bar */}
      <div className="w-full flex justify-between items-center text-xs font-mono text-[var(--color-ink-secondary)] pointer-events-auto border-b border-white/20 pb-3">
        <div className="flex items-center space-x-3">
          <HalbertMark size={20} color="#D4E157" strokeWidth={32} />
          <span className="font-bold text-white tracking-wider">HALBERT KINETIC WORKSPACE</span>
          <span className="text-[var(--color-vector-lime)] font-mono hidden sm:inline">
            // ZOOM: {Math.round(camera.scale * 100)}%
          </span>
        </div>

        <div className="flex items-center space-x-4">
          <div className="text-[11px] text-white/70 font-mono hidden md:inline">
            POS: ({Math.round(camera.cx)}, {Math.round(camera.cy)})
          </div>
          <button
            onClick={() => onJumpToWaypoint(4)}
            className="px-3 py-1 bg-[var(--color-vector-lime)] text-[#042F2E] font-bold text-xs uppercase tracking-wider hover:bg-white transition-colors cursor-pointer"
          >
            Reveal Mark ↗
          </button>
        </div>
      </div>

      {/* Main Dynamic Viewport Waypoint Stage */}
      <div className="w-full max-w-6xl mx-auto my-auto pointer-events-auto">
        {/* WAYPOINT 0: Left / Right Vertical Split */}
        {wp === 0 && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center transition-all duration-300 animate-fadeIn">
            {/* Left Column: Huge Headline */}
            <div className="lg:col-span-7 space-y-6 text-left">
              <div className="inline-block px-3 py-1 bg-[#134E4A] border border-[var(--color-vector-lime)] text-xs font-mono font-bold tracking-widest text-[var(--color-vector-lime)] uppercase">
                01 // VERTICAL VECTOR ENTRY (1000% ZOOM)
              </div>
              <h1 className="text-5xl sm:text-7xl lg:text-[76px] font-display font-black text-white tracking-tight leading-[0.98] cmyk-edge">
                I know what’s <span className="text-[var(--color-vector-lime)] italic">wrong</span> with me<span className="text-[var(--color-vector-lime)]">.</span>
              </h1>
              <p className="text-base sm:text-xl text-[var(--color-ink-secondary)] leading-relaxed max-w-xl">
                The massive vertical stroke before you is a single lane of the Halbert host apparatus. Scroll down to ride the curve.
              </p>
            </div>

            {/* Right Column: Inked Note */}
            <div className="lg:col-span-5 vector-plate p-6 sm:p-8 space-y-4 text-left">
              <div className="text-xs font-mono text-[var(--color-vector-lime)] font-bold uppercase tracking-wider">
                THE EMBODIED HOST MANIFESTO
              </div>
              <p className="text-sm text-white/90 leading-relaxed font-sans">
                Generic AI models are deaf and dumb to physical reality because they live in remote clouds. Halbert runs on your hardware, feels its own thermal diodes, and preserves your configuration history.
              </p>
              <div className="pt-2 text-[11px] font-mono text-[var(--color-ink-tertiary)] flex justify-between">
                <span>SCROLL TO RIDE VECTOR</span>
                <span className="text-[var(--color-vector-lime)] font-bold">↓ APEX AHEAD</span>
              </div>
            </div>
          </div>
        )}

        {/* WAYPOINT 1: Top / Bottom Apex Transformation */}
        {wp === 1 && (
          <div className="space-y-6 text-center max-w-4xl mx-auto transition-all duration-300 animate-fadeIn">
            <div className="inline-block px-3 py-1 bg-[#134E4A] border border-[var(--color-vector-lime)] text-xs font-mono font-bold tracking-widest text-[var(--color-vector-lime)] uppercase">
              02 // AT THE BOTTOM APEX (HORIZONTAL TRANSFORMATION)
            </div>

            <h2 className="text-4xl sm:text-6xl font-display font-black text-white tracking-tight cmyk-edge">
              I can feel my own temperature<span className="text-[var(--color-vector-lime)]">.</span>
            </h2>

            {/* Framed Sensory Plate */}
            <div className="vector-plate p-6 sm:p-8 text-left grid grid-cols-1 md:grid-cols-3 gap-4 font-mono text-xs">
              <div className="p-3 bg-black/20 border border-white/20">
                <div className="text-white/60 text-[10px] uppercase">16 THERMAL DIODES</div>
                <div className="text-2xl font-bold text-white mt-1">44.2°C</div>
                <div className="text-[10px] text-[#34D399] mt-0.5">COOL &amp; QUIET</div>
              </div>

              <div className="p-3 bg-black/20 border border-white/20">
                <div className="text-white/60 text-[10px] uppercase">PRIMARY NVMe LIFE</div>
                <div className="text-2xl font-bold text-white mt-1">100%</div>
                <div className="text-[10px] text-[#34D399] mt-0.5">0 BAD SECTORS</div>
              </div>

              <div className="p-3 bg-black/20 border border-[#F59E0B]/50">
                <div className="text-[10px] text-[#F59E0B] uppercase">SECONDARY /dev/sda1</div>
                <div className="text-2xl font-bold text-[#FBBF24] mt-1">3 TIMEOUTS</div>
                <div className="text-[10px] text-[#F59E0B] mt-0.5">TRIAGE STAGED</div>
              </div>
            </div>

            <p className="text-sm text-[var(--color-ink-secondary)] font-mono">
              [ Next: Scroll to slide perpendicular across to the inner lane → ]
            </p>
          </div>
        )}

        {/* WAYPOINT 2: Perpendicular Lane Hop */}
        {wp === 2 && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center text-left transition-all duration-300 animate-fadeIn">
            <div className="lg:col-span-6 space-y-5">
              <div className="inline-block px-3 py-1 bg-[#134E4A] border border-[var(--color-vector-lime)] text-xs font-mono font-bold tracking-widest text-[var(--color-vector-lime)] uppercase">
                03 // PERPENDICULAR LANE HOP (CONCENTRIC MATRIX)
              </div>
              <h2 className="text-3xl sm:text-5xl font-display font-black text-white tracking-tight cmyk-edge">
                I remember why you changed that<span className="text-[var(--color-vector-lime)]">.</span>
              </h2>
              <p className="text-base text-[var(--color-ink-secondary)] leading-relaxed">
                We have hopped across concentric tracks into Halbert's configuration archaeology. It records human intent alongside AST diffs.
              </p>
            </div>

            <div className="lg:col-span-6 vector-plate p-6 font-mono text-xs space-y-3">
              <div className="flex justify-between border-b border-white/20 pb-2 text-[11px] text-[var(--color-vector-lime)] font-bold">
                <span>/etc/ssh/sshd_config.d/50-custom.conf</span>
                <span>JULY 14, 2026</span>
              </div>
              <div className="p-3 bg-black/30 border border-white/10 space-y-1">
                <div className="text-[#F87171]">- Port 22</div>
                <div className="text-[#34D399] font-bold">+ Port 2222</div>
                <div className="text-white/80 text-[11px] pt-2 border-t border-white/10">
                  <strong className="text-[var(--color-vector-lime)]">HUMAN RATIONALE:</strong> "Automated brute-force bots logged 4.2k attempts per day."
                </div>
              </div>
              <div className="text-[10px] text-white/60">
                BLAST RADIUS: LOW · STORED IN LOCAL SQLITE MEMORY
              </div>
            </div>
          </div>
        )}

        {/* WAYPOINT 3: Ascending Inner Spine */}
        {wp === 3 && (
          <div className="space-y-6 text-center max-w-3xl mx-auto transition-all duration-300 animate-fadeIn">
            <div className="inline-block px-3 py-1 bg-[#134E4A] border border-[var(--color-vector-lime)] text-xs font-mono font-bold tracking-widest text-[var(--color-vector-lime)] uppercase">
              04 // ASCENDING THE INNER SPINE
            </div>

            <h2 className="text-4xl sm:text-6xl font-display font-black text-white tracking-tight cmyk-edge">
              I know 16,000 manuals by heart<span className="text-[var(--color-vector-lime)]">.</span>
            </h2>

            <div className="vector-plate p-6 text-left space-y-4 text-xs font-mono">
              <div className="flex justify-between border-b border-white/20 pb-2 text-white/70">
                <span>LOCAL SOURCEPREP RAG</span>
                <span className="text-[#34D399]">● ZERO CLOUD EGRESS</span>
              </div>
              <div className="p-3 bg-black/30 border border-white/10 space-y-2 text-white/90">
                <div>&gt; halbert propose storage-compress /data --dry-run</div>
                <div className="text-[var(--color-vector-lime)]">
                  Proposed: `mount -o remount,compression=lz4 /data`
                </div>
                <div className="text-white/60 text-[11px]">
                  Estimated space recovery: 35% with zero unmount downtime.
                </div>
              </div>
            </div>

            <p className="text-xs text-[var(--color-ink-secondary)] font-mono">
              [ Scroll to pull back the camera for the Grand Zoom-Out Reveal ↓ ]
            </p>
          </div>
        )}

        {/* WAYPOINT 4: Grand Zoom-Out Reveal */}
        {wp === 4 && (
          <div className="space-y-8 text-center max-w-2xl mx-auto transition-all duration-500 animate-fadeIn">
            <div className="inline-block px-3 py-1 bg-[#134E4A] border border-[var(--color-vector-lime)] text-xs font-mono font-bold tracking-widest text-[var(--color-vector-lime)] uppercase">
              05 // THE REVEAL · 100% SCALE
            </div>

            <h2 className="text-4xl sm:text-6xl lg:text-7xl font-display font-black text-white tracking-tight leading-[0.98] cmyk-edge">
              “I am not an assistant.<br />
              <span className="text-[var(--color-vector-lime)] italic">I am the machine.”</span>
            </h2>

            <p className="text-base sm:text-lg text-[var(--color-ink-secondary)]">
              The entire Halbert concentric vector mark is now in full view. 100% local host intelligence for macOS and Linux.
            </p>

            {/* Email Dispatch Registry */}
            <div className="vector-plate p-6 sm:p-8">
              {status === 'success' ? (
                <div className="p-4 bg-black/30 border border-[var(--color-vector-lime)] text-[var(--color-vector-lime)] font-display font-bold text-sm">
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

      {/* Bottom Footer Navigation Coordinates */}
      <div className="w-full flex justify-between items-center text-[11px] font-mono text-[var(--color-ink-tertiary)] pointer-events-auto border-t border-white/20 pt-3">
        <div>STAGE: 0{wp + 1} OF 05</div>
        <div>HALBERT HOST ENGINE // OLLAMA EMBEDDED</div>
      </div>
    </div>
  );
}
