import React, { useState, useEffect } from 'react';

export function Oscilloscope({ className = '' }) {
  const [tick, setTick] = useState(0);
  const [temp, setTemp] = useState(44.2);
  const [load, setLoad] = useState(0.18);

  useEffect(() => {
    const interval = setInterval(() => {
      setTick((t) => (t + 1) % 100);
      setTemp((prev) => +(44.0 + Math.sin(Date.now() / 2000) * 1.5 + Math.random() * 0.4).toFixed(1));
      setLoad((prev) => +(0.15 + Math.abs(Math.sin(Date.now() / 4000)) * 0.12).toFixed(2));
    }, 150);
    return () => clearInterval(interval);
  }, []);

  // Generate dynamic sine/waveform path points
  const points = [];
  const width = 360;
  const height = 90;
  for (let x = 0; x <= width; x += 6) {
    const freq = 0.04;
    const y =
      height / 2 +
      Math.sin((x + tick * 4) * freq) * 18 * Math.sin(x * 0.015) +
      (Math.random() - 0.5) * 3;
    points.push(`${x},${y.toFixed(1)}`);
  }
  const pathData = `M ${points.join(' L ')}`;

  return (
    <div
      className={`border-2 border-[var(--color-ink)] bg-[var(--color-surface)] shadow-[6px_6px_0px_0px_rgba(18,20,23,1)] p-5 font-mono text-xs ${className}`}
    >
      {/* Title & Diagnostic Grid */}
      <div className="flex justify-between items-center border-b border-[var(--color-ink)] pb-2.5 mb-4">
        <div className="flex items-center space-x-2 font-bold uppercase tracking-wider text-[var(--color-ink)]">
          <span className="w-2.5 h-2.5 bg-[var(--color-accent)] inline-block" />
          <span>PHYSIOLOGICAL OSCILLOSCOPE // HW-01</span>
        </div>
        <div className="text-[11px] font-bold text-[var(--color-status-success)] bg-[#EEF6F2] px-2 py-0.5 border border-[#1E7B48]">
          HWMON / LIVE
        </div>
      </div>

      {/* Waveform Scope Area */}
      <div className="relative h-28 bg-[var(--color-canvas)] border border-[var(--color-ink)] overflow-hidden flex items-center justify-center drafting-grid">
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full">
          {/* Center reference lines */}
          <line x1="0" y1={height / 2} x2={width} y2={height / 2} stroke="rgba(18,20,23,0.2)" strokeDasharray="3 3" />
          {/* Signal path */}
          <path d={pathData} fill="none" stroke="var(--color-accent)" strokeWidth="2" strokeLinecap="square" />
        </svg>
        <div className="absolute top-1.5 left-2 text-[10px] text-[var(--color-ink-tertiary)] uppercase font-bold">
          FREQ: 2.4GHz · PK-PK: 1.2V
        </div>
        <div className="absolute bottom-1.5 right-2 text-[10px] text-[var(--color-accent)] font-bold">
          LIVE SENSOR LOOP
        </div>
      </div>

      {/* Metric Readouts Grid */}
      <div className="grid grid-cols-3 gap-3 pt-4 border-t border-[var(--color-ink)] mt-4">
        <div className="p-2.5 bg-[var(--color-surface-subtle)] border border-[var(--color-ink)]">
          <div className="text-[10px] text-[var(--color-ink-tertiary)] uppercase">CPU DIODE</div>
          <div className="text-lg font-bold text-[var(--color-ink)] mt-0.5">{temp}°C</div>
          <div className="text-[9.5px] text-[var(--color-status-success)] font-bold">COOL / QUIET</div>
        </div>

        <div className="p-2.5 bg-[var(--color-surface-subtle)] border border-[var(--color-ink)]">
          <div className="text-[10px] text-[var(--color-ink-tertiary)] uppercase">LOAD (1M)</div>
          <div className="text-lg font-bold text-[var(--color-ink)] mt-0.5">{load}</div>
          <div className="text-[9.5px] text-[var(--color-ink-tertiary)] font-bold">14% CAPACITY</div>
        </div>

        <div className="p-2.5 bg-[var(--color-surface-subtle)] border border-[var(--color-ink)]">
          <div className="text-[10px] text-[var(--color-ink-tertiary)] uppercase">NVMe HEALTH</div>
          <div className="text-lg font-bold text-[var(--color-ink)] mt-0.5">100%</div>
          <div className="text-[9.5px] text-[var(--color-status-success)] font-bold">0 WEAR REALLOC</div>
        </div>
      </div>

      {/* Grounded First-Person Quote */}
      <div className="mt-4 p-3 bg-[var(--color-blueprint-light)] border border-[var(--color-blueprint)] text-[var(--color-blueprint)] text-[11.5px] leading-relaxed">
        <strong>HALBERT:</strong> "I checked my thermal envelopes across all 8 cores. Everything is running cold."
      </div>
    </div>
  );
}
