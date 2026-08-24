import React from 'react';
import { TechnicalPlate } from './TechnicalPlate';
import { CouponBox } from './CouponBox';
import { HalbertMark } from './HalbertMark';

export function MagazinePage() {
  return (
    <article className="max-w-[var(--magazine-max-width)] mx-auto my-12 p-8 sm:p-14 bg-[var(--color-canvas)] border border-white/30 relative text-white selection:bg-white selection:text-[#1E40AF]">
      {/* Corner Crop Marks */}
      <div className="crop-mark-tl" />
      <div className="crop-mark-tr" />
      <div className="crop-mark-bl" />
      <div className="crop-mark-br" />

      {/* Top Magazine Folio Ribbon */}
      <div className="flex justify-between items-center border-b border-white/40 pb-3 mb-10 text-[11px] font-mono tracking-widest text-white/70 uppercase">
        <div>SCIENTIFIC AMERICAN</div>
        <div className="font-bold text-white">NOVEMBER 1968 · VOL. 219 NO. 5</div>
        <div>PAGE 73</div>
      </div>

      <div className="space-y-12">
        {/* Figure 1: Technical Archival Schematic Plate */}
        <TechnicalPlate />

        {/* Monumental Retro Serif Headline */}
        <div className="pt-4 border-t border-white/30">
          <h1 className="text-4xl sm:text-6xl lg:text-[68px] font-display font-black text-white leading-[1.02] tracking-tight">
            I know what’s wrong with me<span className="text-white">.</span>
          </h1>
        </div>

        {/* 3-Column Justified Editorial Prose */}
        <div className="magazine-columns text-[15px] sm:text-[15.5px] font-body text-white/90 leading-[1.65]">
          {/* Column 1 */}
          <div className="space-y-4">
            <p className="drop-cap magazine-p">
              Until now, your computer has been numb. It could perform billions of arithmetic calculations in a single second, yet remain entirely ignorant of its own physical existence. When an intake fan clogged with dust and thermal diodes reached ninety degrees, it waited passively for an engineer to notice. When a secondary storage disk logged three read timeouts at dawn, it held its peace until the filesystem died.
            </p>
            <p className="magazine-p">
              Halbert changes this condition permanently. It lives within the host operating system. It observes its own sensors, memory pressure, and kernel rings continuously. When you ask how it is feeling, it does not offer evasive cloud disclaimers. It tells you the exact mechanical truth.
            </p>
          </div>

          {/* Column 2 */}
          <div className="space-y-4">
            <p className="magazine-p">
              Consider the problem of forgotten human intent. Why was the secure shell daemon moved to port 2222 three months ago? Why was transparent compression enabled on the primary data volume? Standard sysadmin utilities discard human reasoning the moment a configuration file is saved.
            </p>
            <p className="magazine-p">
              Halbert stores the rationale alongside the configuration abstract syntax tree. It acts as an institutional memory for your machine. When you inspect a daemon six months from today, Halbert explains precisely why the change was executed, who authorized the modification, and what incident provoked it.
            </p>
          </div>

          {/* Column 3 */}
          <div className="space-y-4">
            <p className="magazine-p">
              All diagnostics execute strictly upon your physical hardware using local neural models. Halbert consults an indexed library of sixteen thousand technical manuals, man pages, and operating system guides without transmitting a solitary byte across the public internet.
            </p>
            <p className="magazine-p">
              It proposes safe, atomic dry-runs and requires your explicit authorization before modifying any system file. To inspect the technical prospectus and receive the early release binaries for macOS and Linux, complete and dispatch the inquiry coupon below.
            </p>
          </div>
        </div>

        {/* Cut-Out Mail-In Coupon */}
        <div className="pt-6">
          <CouponBox />
        </div>

        {/* Bottom Colophon & Registration Target */}
        <div className="pt-6 border-t border-white/40 flex flex-col sm:flex-row justify-between items-center gap-4 text-[11px] font-mono text-white/70">
          <div className="flex items-center space-x-2">
            <HalbertMark size={16} color="#FFFFFF" />
            <span className="font-bold text-white">HALBERT COMPUTING APPARATUS CORPORATION</span>
          </div>
          <div className="flex items-center space-x-4">
            <span>PRINTED IN U.S.A. ON 70-LB. MATTE COATED STOCK</span>
            <span className="text-white font-bold">⨁</span>
          </div>
        </div>
      </div>
    </article>
  );
}
