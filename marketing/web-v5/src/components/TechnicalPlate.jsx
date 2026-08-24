import React from 'react';
import { HalbertMark } from './HalbertMark';

export function TechnicalPlate() {
  return (
    <div className="w-full space-y-3 font-serif">
      {/* Archival Inked Technical Plate */}
      <div className="border border-white/40 p-6 sm:p-10 bg-[#1E3A8A] relative">
        {/* Technical Coordinate Tags */}
        <div className="flex justify-between items-center text-[10px] font-mono text-white/60 tracking-widest uppercase border-b border-white/20 pb-2 mb-6">
          <span>SCHEMATIC NO. 2026-A // SENSORY LOOP</span>
          <span>SCALE: 1:1 LOCAL EMBODIMENT</span>
        </div>

        {/* Central Vector Apparatus Linework */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-8 items-center">
          {/* Vector Schematic Graphic */}
          <div className="md:col-span-5 flex flex-col items-center justify-center p-6 border border-white/20 bg-[#152E6F]/50">
            <HalbertMark size={96} color="#FFFFFF" strokeWidth={24} />
            <div className="mt-4 text-center">
              <div className="font-display font-bold text-sm text-white tracking-wide">
                HALBERT APPARATUS
              </div>
              <div className="text-[11px] font-mono text-white/70">
                100% HOST-BOUND AUTONOMY
              </div>
            </div>
          </div>

          {/* Technical Telemetry Callout Table */}
          <div className="md:col-span-7 space-y-3 font-mono text-[11px] text-white">
            <div className="border-b border-white/20 pb-1 text-[10px] text-white/60 uppercase tracking-wider">
              SPECIFICATIONS &amp; EMBODIED SENSORS
            </div>
            
            <div className="grid grid-cols-2 gap-3">
              <div className="p-2.5 border border-white/20 bg-[#152E6F]/30">
                <div className="text-white/50 text-[9px] uppercase">DIODE INTAKE</div>
                <div className="font-bold text-xs text-white mt-0.5">16 Thermal Zones</div>
                <div className="text-white/70 text-[9px]">44.2°C Continuous Sample</div>
              </div>

              <div className="p-2.5 border border-white/20 bg-[#152E6F]/30">
                <div className="text-white/50 text-[9px] uppercase">AST MEMORY</div>
                <div className="font-bold text-xs text-white mt-0.5">Rationale Engine</div>
                <div className="text-white/70 text-[9px]">Full Config Provenance</div>
              </div>

              <div className="p-2.5 border border-white/20 bg-[#152E6F]/30">
                <div className="text-white/50 text-[9px] uppercase">DOCUMENTATION</div>
                <div className="font-bold text-xs text-white mt-0.5">16,000 Manuals</div>
                <div className="text-white/70 text-[9px]">Local SourcePrep RAG</div>
              </div>

              <div className="p-2.5 border border-white/20 bg-[#152E6F]/30">
                <div className="text-white/50 text-[9px] uppercase">NETWORK EGRESS</div>
                <div className="font-bold text-xs text-[#34D399] mt-0.5">0.00 Bytes</div>
                <div className="text-white/70 text-[9px]">Zero Cloud Telemetry</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Traditional Academic Plate Caption */}
      <div className="text-[12.5px] font-serif italic text-white/80 leading-snug px-1">
        <strong className="not-italic font-semibold text-white">Fig. 1.</strong> — The Halbert Host Computing Apparatus (Model 2026). Continuous local sensory intake and configuration archaeology without reliance upon distant telecommunication networks.
      </div>
    </div>
  );
}
