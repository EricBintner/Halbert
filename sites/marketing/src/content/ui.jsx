import React, { useLayoutEffect, useRef } from 'react';
import { Mic, Keyboard } from 'lucide-react';
import { VoiceModeLoop } from '@halbert/design-system';

/**
 * Placeholder app surfaces.
 *
 * These stand in for the real dashboard components until the animated
 * library versions exist. Information architecture and microcopy follow the
 * shipped app (Proactive Events, Vitals, WhyBrain / WhyChip, Knowledge Base
 * Storage, ScanBlock); the visual treatment follows the design spec — warm
 * paper, hairlines, 8px radius, tinted status pills — so a plate reads as a
 * window of Halbert regardless of which colour field it sits on.
 */

const PAPER = {
  bg: 'var(--color-canvas)',
  surface: 'var(--color-surface)',
  subtle: 'var(--color-surface-subtle)',
  ink: 'var(--color-ink)',
  ink2: 'var(--color-ink-secondary)',
  ink3: 'var(--color-ink-tertiary)',
  line: 'var(--color-line)',
  accent: 'var(--color-accent)',
  accentStrong: 'var(--color-accent-strong)',
  accentTint: 'var(--color-accent-tint)',
  inkOnAccent: 'var(--color-ink-on-accent)',
};

const TONES = {
  success:  { fg: 'var(--color-status-nominal)',   bg: 'var(--color-status-nominal-bg)',   line: 'var(--color-status-nominal-line)' },
  warning:  { fg: 'var(--color-status-warning)',   bg: 'var(--color-status-warning-bg)',   line: 'var(--color-status-warning-line)' },
  critical: { fg: 'var(--color-status-critical)',  bg: 'var(--color-status-critical-bg)',  line: 'var(--color-status-critical-line)' },
  info:     { fg: 'var(--color-status-telemetry)', bg: 'var(--color-status-telemetry-bg)', line: 'var(--color-status-telemetry-line)' },
  neutral:  { fg: 'var(--color-ink-secondary)',    bg: 'var(--color-surface-subtle)',      line: 'var(--color-line)' },
};

/** Tinted outline status pill (mirrors StatusBadge in the app). */
export function Pill({ tone = 'neutral', children }) {
  const t = TONES[tone] ?? TONES.neutral;
  return (
    <span
      className="inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-mono font-semibold tracking-wide uppercase whitespace-nowrap"
      style={{ color: t.fg, backgroundColor: t.bg, borderColor: t.line }}
    >
      {children}
    </span>
  );
}

export function Btn({ variant = 'outline', children }) {
  const styles =
    variant === 'primary'
      ? { backgroundColor: PAPER.accentStrong, color: PAPER.inkOnAccent, borderColor: PAPER.accentStrong }
      : { backgroundColor: 'transparent', color: PAPER.ink, borderColor: PAPER.line };
  return (
    <span className="inline-flex items-center rounded-md border px-2.5 py-1 text-[11px] font-semibold" style={styles}>
      {children}
    </span>
  );
}

/** An app window: header strip + body + optional footer. */
export function AppWindow({ title, meta, children, footer, className = '' }) {
  return (
    <div
      className={`mt-6 w-full max-w-md rounded-lg border overflow-hidden text-left font-sans ${className}`}
      style={{ backgroundColor: PAPER.surface, borderColor: PAPER.line, color: PAPER.ink, boxShadow: 'var(--shadow-plate)' }}
    >
      <div
        className="flex items-center justify-between px-3 py-2 text-[12px] font-medium"
        style={{ backgroundColor: PAPER.bg, borderBottom: `1px solid ${PAPER.line}` }}
      >
        <span className="flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: PAPER.accent }} />
          {title}
        </span>
        {meta && <span className="font-mono text-[10px]" style={{ color: PAPER.ink3 }}>{meta}</span>}
      </div>
      <div className="p-3">{children}</div>
      {footer && (
        <div className="px-3 py-2 text-[10px] font-mono" style={{ color: PAPER.ink3, borderTop: `1px solid ${PAPER.line}`, backgroundColor: PAPER.bg }}>
          {footer}
        </div>
      )}
    </div>
  );
}

/** A stat tile (mirrors VitalsModule / Dashboard stat cards). */
export function StatTile({ label, value, sub, tone, bar, phone = true }) {
  const t = tone ? TONES[tone] : null;
  return (
    <div
      className={`rounded-md border p-2.5 ${phone ? '' : 'hidden sm:block'}`}
      style={{ borderColor: PAPER.line, backgroundColor: PAPER.surface }}
    >
      <div className="text-[10px] font-mono uppercase tracking-wider" style={{ color: PAPER.ink3 }}>{label}</div>
      <div className="text-lg font-semibold leading-tight mt-0.5" style={{ color: PAPER.ink }}>{value}</div>
      {bar != null && (
        <div className="hidden sm:block h-1 rounded-full mt-1.5 overflow-hidden" style={{ backgroundColor: PAPER.subtle }}>
          <div className="h-full rounded-full" style={{ width: `${bar}%`, backgroundColor: t ? t.fg : PAPER.accent }} />
        </div>
      )}
      {sub && <div className="hidden sm:block text-[11px] mt-1" style={{ color: t ? t.fg : PAPER.ink2 }}>{sub}</div>}
    </div>
  );
}

const SEVERITY_GLYPH = { critical: '●', warning: '▲', info: 'ℹ' };

/** A Proactive Events row: severity square, title, body, Snooze / Dismiss. */
export function EventRow({ severity = 'info', title, body, actions = true, phone = true }) {
  const t = TONES[severity === 'critical' ? 'critical' : severity === 'warning' ? 'warning' : 'info'];
  return (
    <div className={`gap-2.5 py-2.5 ${phone ? 'flex' : 'hidden sm:flex'}`} style={{ borderTop: `1px solid ${PAPER.line}` }}>
      <span
        className="shrink-0 w-6 h-6 rounded-md border flex items-center justify-center text-[10px]"
        style={{ color: t.fg, backgroundColor: t.bg, borderColor: t.line }}
        aria-hidden="true"
      >
        {SEVERITY_GLYPH[severity] ?? 'ℹ'}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-medium leading-snug" style={{ color: PAPER.ink }}>{title}</div>
        <div className="text-[11px] leading-snug mt-0.5" style={{ color: PAPER.ink2 }}>{body}</div>
        {actions && (
          <div className="flex gap-3 mt-1.5 text-[10px] font-mono" style={{ color: PAPER.ink3 }}>
            <span>◷ Snooze 7d</span>
            <span>✕ Dismiss</span>
          </div>
        )}
      </div>
    </div>
  );
}

/** Label / value row for evidence lists (mirrors WhyChip's "Evidence & Sources"). */
export function EvidenceRow({ label, refText }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1 text-[11px]">
      <span style={{ color: PAPER.ink }}>{label}</span>
      <span className="font-mono text-[10px] truncate" style={{ color: PAPER.ink3 }}>{refText}</span>
    </div>
  );
}

/* ------------------------------------------------------------------------ */
/* The four plates used by the storyboard                                    */
/* ------------------------------------------------------------------------ */

/** 01 — "I know what's wrong with me." The proactive events tray. */
export function ProactiveEventsPlate() {
  return (
    <AppWindow title="Proactive Events" meta="2 active">
      <div className="-mt-2.5">
        <EventRow
          severity="warning"
          title="sshd config conflict: PermitRootLogin"
          body="Set to different values across sshd_config and a drop-in. Effective value is 'yes' — from /etc/ssh/sshd_config.d/50-cloud.conf:12."
        />
        <EventRow
          severity="warning"
          title="/dev/sda1 logged 3 read errors this morning"
          body="Pending sectors: 3. Reallocated: 0. I'd schedule an extended SMART self-test before this becomes a restore."
        />
        <EventRow
          severity="info"
          title="Backup completed — borg, 03:02"
          body="Destination volume has 11% free. Fine for now; I'll say so when it isn't."
          actions={false}
          phone={false}
        />
      </div>
    </AppWindow>
  );
}

/** 02 — "I can feel my own temperature." A vitals strip. */
export function VitalsPlate() {
  return (
    <AppWindow title="System Vitals" meta="updates every 5s" className="max-w-2xl md:mt-5">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <StatTile label="CPU temp" value="45°C" sub="Nominal · fans idle" tone="success" bar={38} />
        <StatTile label="Load avg" value="0.15" sub="0.22 · 0.18 over 5 / 15 min" bar={9} />
        <StatTile label="Memory" value="18.2 GB" sub="of 64.0 GB" bar={28} phone={false} />
        <StatTile label="Uptime" value="42 days" sub="14 hours" phone={false} />
      </div>
    </AppWindow>
  );
}

/** 04 — "I remember why you changed that." Rationale + provenance for one config item. */
export function RationalePlate() {
  return (
    <AppWindow title="Why does this exist?" meta="config · sshd_config.d/50-custom.conf">
      <div className="flex items-center justify-between gap-3">
        <div className="font-mono text-[11px]" style={{ color: PAPER.ink }}>
          <span style={{ color: PAPER.ink3 }}>Port 22</span> → <strong>Port 2222</strong>
        </div>
        <Pill tone="success">Applied · Jul 14</Pill>
      </div>
      <div className="mt-3 rounded-md p-2.5 text-[12px] leading-snug" style={{ backgroundColor: PAPER.accentTint, color: PAPER.ink }}>
        <div className="text-[10px] font-mono uppercase tracking-wider mb-1" style={{ color: PAPER.accentStrong }}>
          Your rationale
        </div>
        “The auth log was filling with scan attempts on 22. Moved it. It's been quiet since.”
      </div>
      <div className="mt-3">
        <div className="text-[10px] font-mono uppercase tracking-wider mb-1" style={{ color: PAPER.ink3 }}>
          Evidence &amp; Sources
        </div>
        <EvidenceRow label="Config line" refText="/etc/ssh/sshd_config.d/50-custom.conf:3" />
        <EvidenceRow label="Journal window" refText="2026-07-14 04:00 → 06:12 · 4,212 failed logins" />
        <EvidenceRow label="Snapshot before change" refText="#SNAP-20260714-02" />
      </div>
    </AppWindow>
  );
}

/** 05 — "I know 16,000 manuals by heart." Knowledge base + a live search. */
export function KnowledgePlate() {
  return (
    <AppWindow title="Knowledge Base Storage" meta="on this disk · NVMe SSD">
      <div className="grid grid-cols-3 gap-2">
        <StatTile label="RAG docs" value="24,643" sub="man pages · wiki · formulae" />
        <StatTile label="Learned facts" value="312" sub="about this machine" />
        <StatTile label="Collections" value="6" sub="shared SQLite store" />
      </div>
      <div
        className="mt-3 flex items-center justify-between gap-3 rounded-md border px-2.5 py-2 text-[11px]"
        style={{ borderColor: PAPER.line, backgroundColor: PAPER.bg }}
      >
        <div className="min-w-0">
          <div className="font-medium" style={{ color: PAPER.ink }}>Searched Documents</div>
          <div className="font-mono text-[10px] truncate" style={{ color: PAPER.ink3 }}>
            Query: extended SMART self-test, pending sectors
          </div>
        </div>
        <Pill tone="info">3 found</Pill>
      </div>
    </AppWindow>
  );
}

/**
 * 00 — Voice Mode on the kiosk tablet, for the Intro stop.
 *
 * The surround (bezel, status strip, caption ribbon, touch bar) is a mock in
 * the same sense as the plates above; the mark is the real thing — the
 * shipped audio-reactive mark from the design system, mid-thought.
 *
 * True scale model: the device is authored once at 480x640 — every internal
 * size below is the exact px value verified there — and the layout effect
 * fits that rasterized layout to the frame with a single CSS scale. Layout
 * never reflows: the pill row that fits at 480px fits identically at 175px,
 * so the screen can never wrap or crowd at small sizes. The frame's own
 * width budget lives in index.css (.voice-plate).
 */
export function VoiceModePlate() {
  const glassEdge = 'color-mix(in srgb, var(--color-canvas) 20%, transparent)';
  const frameRef = useRef(null);
  const deviceRef = useRef(null);

  useLayoutEffect(() => {
    const frame = frameRef.current;
    const device = deviceRef.current;
    if (!frame || !device) return;
    const fit = () => {
      const w = frame.clientWidth;
      if (w > 0) device.style.transform = `scale(${w / 480})`;
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(frame);
    return () => ro.disconnect();
  }, []);

  return (
    <div ref={frameRef} className="voice-plate relative">
      <div
        ref={deviceRef}
        className="voice-device relative"
        style={{
          width: 480,
          height: 640,
          padding: 20,
          borderRadius: 24,
          backgroundColor: PAPER.ink,
          boxShadow: 'var(--shadow-plate)',
          transformOrigin: 'top left',
        }}
      >
      <div
        className="voice-screen relative flex h-full w-full flex-col overflow-hidden"
        style={{
          borderRadius: 18,
          backgroundColor: 'color-mix(in srgb, var(--color-ink) 93%, var(--color-canvas))',
          border: `1px solid ${glassEdge}`,
        }}
      >
          {/* status strip */}
          <div
            className="flex items-center justify-between px-[30px] pt-[24px] text-[10px] font-mono uppercase tracking-[var(--tracking-label)]"
            style={{ color: 'color-mix(in srgb, var(--color-canvas) 55%, transparent)' }}
          >
            <span>Halbert</span>
            <span>10:47 AM</span>
          </div>

        {/* the mark — the design system's Voice Mode loop (listening,
         * recognized, thinking, speaking), the same component Storybook shows,
         * playing the shared demo voice */}
        <div className="flex min-h-0 flex-1 items-center justify-center">
          <div className="aspect-square w-[52%]">
            <VoiceModeLoop size="100%" tone="accent" sensitivity={1.2} />
          </div>
        </div>

          {/* caption */}
          <p
            className="px-[38px] pb-[12px] text-center text-[11px] leading-snug"
            style={{ color: 'color-mix(in srgb, var(--color-canvas) 90%, transparent)' }}
          >
            Looking over what changed while you were out…
          </p>

          {/* touch-bar hint */}
          <div className="flex items-center justify-center gap-[10px] pb-[36px]">
            <span
              className="inline-flex items-center gap-[6px] rounded-full border px-[12px] py-[5px] text-[10px] font-medium"
              style={{
                color: 'var(--color-canvas)',
                borderColor: 'color-mix(in srgb, var(--color-accent) 45%, transparent)',
                backgroundColor: 'color-mix(in srgb, var(--color-accent) 16%, transparent)',
              }}
            >
              <Mic className="h-[12px] w-[12px]" aria-hidden="true" style={{ color: 'var(--color-accent)' }} />
              Tap to speak
            </span>
            <span
              className="inline-flex items-center gap-[6px] rounded-full border px-[12px] py-[5px] text-[10px] font-medium"
              style={{
                color: 'color-mix(in srgb, var(--color-canvas) 40%, transparent)',
                borderColor: glassEdge,
              }}
            >
              <Keyboard className="h-[12px] w-[12px]" aria-hidden="true" />
              Keyboard
            </span>
          </div>

          {/* home indicator */}
          <span
            className="absolute bottom-[10px] left-1/2 h-[3px] w-[26%] -translate-x-1/2 rounded-full"
            style={{ backgroundColor: 'color-mix(in srgb, var(--color-canvas) 35%, transparent)' }}
          />
        </div>
      </div>

      {/* platform line — eyebrow type (Kicker's exact classes), absolutely
         placed below the frame so neither the device's fit-to-frame scale
         nor the slot's flow is affected at any viewport. Phones widen the
         box to the band (see .voice-platform in index.css) so the line can
         never overflow the narrower scale-model frame. */}
      <div
        className="voice-platform absolute inset-x-0 text-center text-[13px] font-mono font-bold uppercase tracking-[0.2em] opacity-80 max-sm:tracking-[0.12em] whitespace-nowrap"
        style={{ top: 'calc(100% + 10px)' }}
      >
        Mac • Linux • Home Assistant
      </div>
    </div>
  );
}
