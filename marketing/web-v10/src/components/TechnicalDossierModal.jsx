import React, { useEffect, useMemo, useRef, useState } from 'react';
import { BookOpen, X, ChevronRight, ChevronDown, ExternalLink } from 'lucide-react';
import { STOPS } from '../lib/storyboard';
import {
  citationsForStop,
  featuresForStop,
  formatCitation,
} from '../lib/researchData';

/**
 * TechnicalDossierModal — ultra-minimal stop-curated research dossier.
 *
 * Triggered by a standalone graphic icon in the lower-left corner.
 * Displays only the active storyboard stop's curated research papers
 * and architectural features. No search bar, no tabs, no extra buttons,
 * and no cards inside of cards: just clean, scannable headlines with
 * inline click-to-expand details.
 */

const TYPE_LABELS = {
  paper: 'PAPER',
  rfc: 'RFC',
  spec: 'SPEC',
  benchmark: 'BENCHMARK',
  survey: 'SURVEY',
  'engineering-report': 'ENG. REPORT',
  licence: 'LICENCE',
};

const CURATED_STOP_FEATURE_IDS = {
  intro: ['mcp-server', 'local-voice-pipeline', 'acoustic-sensing'],
  open: ['37-system-scanners', 'four-whys-findings', 'morning-reports-reflexes'],
  apex: ['home-assistant-control', 'occupancy-behavior', 'apps-container-management'],
  diagonal: ['air-gapped-private-execution', 'secure-credential-storage', 'hot-swap-providers'],
  rise: ['memory-vault', 'why-brain', 'diff-proposals-rollback', 'provenance-tracking'],
  hop: ['hybrid-retrieval', 'indexed-documents', 'context-compression'],
  cap: ['peer-pairing', 'canonical-host-satellites', 'remote-tool-proxy'],
  reveal: ['three-panel-shell', 'terminal-tiles-sandbox', 'skill-registry'],
};

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(() =>
    typeof window !== 'undefined' && 'matchMedia' in window
      ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
      : false,
  );
  useEffect(() => {
    if (typeof window === 'undefined' || !('matchMedia' in window)) return undefined;
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = (e) => setReduced(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return reduced;
}

function useFocusTrap(active, ref) {
  useEffect(() => {
    if (!active) return undefined;
    const node = ref.current;
    if (!node) return undefined;
    const selector =
      'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';
    const onKeyDown = (e) => {
      if (e.key !== 'Tab') return;
      const focusables = Array.from(node.querySelectorAll(selector)).filter(
        (el) => el.offsetParent !== null || el === document.activeElement,
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    node.addEventListener('keydown', onKeyDown);
    return () => node.removeEventListener('keydown', onKeyDown);
  }, [active, ref]);
}

const PANEL_ID = 'technical-dossier-panel';

export function TechnicalDossierModal({ camera, stops }) {
  const stopIndex = camera?.stopIndex ?? 0;
  const allStops = stops ?? STOPS;
  const activeStop = allStops[stopIndex] ?? allStops[0];
  const activeStopId = activeStop?.id ?? '';

  const [open, setOpen] = useState(false);
  const [expandedId, setExpandedId] = useState(null);

  const reducedMotion = usePrefersReducedMotion();
  const triggerRef = useRef(null);
  const panelRef = useRef(null);
  useFocusTrap(open, panelRef);

  // Esc closes
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  // Focus management
  const prevOpen = useRef(false);
  useEffect(() => {
    if (prevOpen.current === open) return;
    if (open) {
      if (panelRef.current) panelRef.current.focus();
    } else {
      setExpandedId(null);
      if (triggerRef.current) triggerRef.current.focus();
    }
    prevOpen.current = open;
  }, [open]);

  // Reset expanded item on stop change so view stays lightweight
  useEffect(() => {
    setExpandedId(null);
  }, [activeStopId]);

  // Citations for the active stop
  const stopCitations = useMemo(() => citationsForStop(activeStopId), [activeStopId]);

  // Curated features for the active stop
  const stopFeatures = useMemo(() => {
    const allForStop = featuresForStop(activeStopId);
    const curatedIds = CURATED_STOP_FEATURE_IDS[activeStopId];
    if (curatedIds && curatedIds.length > 0) {
      const idMap = new Map(allForStop.map((f) => [f.id, f]));
      const curated = curatedIds.map((id) => idMap.get(id)).filter(Boolean);
      return curated.length > 0 ? curated : allForStop;
    }
    return allForStop;
  }, [activeStopId]);

  const toggleItem = (id) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  const motion = 'transform var(--duration-shutter) var(--ease-shutter), opacity var(--duration-shutter) var(--ease-shutter)';
  const panelStyle = reducedMotion
    ? open
      ? { opacity: 1 }
      : { opacity: 0, visibility: 'hidden' }
    : open
      ? { transform: 'scale(1)', opacity: 1, visibility: 'visible', transition: `${motion}, visibility 0s` }
      : {
          transform: 'scale(0.96)',
          opacity: 0,
          visibility: 'hidden',
          transition: `${motion}, visibility 0s var(--duration-shutter)`,
        };

  const openClass = open ? 'pointer-events-auto' : 'pointer-events-none';

  return (
    <>
      {/* Graphic Icon Trigger — standalone mechanical icon button in bottom-left corner */}
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={PANEL_ID}
        aria-haspopup="dialog"
        aria-label="Research & Architecture Dossier"
        data-testid="dossier-trigger"
        style={{
          bottom: 'calc(env(safe-area-inset-bottom, 0px) + 1rem)',
          left: 'calc(env(safe-area-inset-left, 0px) + 1rem)',
        }}
        className="fixed z-40 flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)]/95 text-[var(--color-ink)] shadow-[var(--shadow-plate)] backdrop-blur-md transition-all duration-150 hover:border-[var(--color-stroke)] hover:text-[var(--color-stroke)] active:scale-95 cursor-pointer"
      >
        <BookOpen size={16} aria-hidden="true" />
      </button>

      {/* Popup Drawer — compact, simplified, corner-anchored */}
      <div
        ref={panelRef}
        id={PANEL_ID}
        role="dialog"
        aria-modal={open ? 'true' : undefined}
        aria-label="Technical research dossier"
        aria-hidden={!open}
        data-testid="dossier-panel"
        data-active-stop={activeStopId}
        inert={!open}
        tabIndex={-1}
        style={panelStyle}
        className={`fixed z-50 flex flex-col overflow-hidden rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)]/95 text-[var(--color-ink)] shadow-[var(--shadow-popover)] backdrop-blur-xl max-sm:inset-x-3 max-sm:bottom-16 max-sm:max-h-[70vh] sm:bottom-14 sm:left-4 sm:w-[380px] sm:max-w-[calc(100vw-2rem)] sm:max-h-[62vh] sm:origin-bottom-left ${openClass}`}
      >
        {/* Header: Headline + Close button only */}
        <div className="flex shrink-0 items-center justify-between border-b border-[var(--color-line)] bg-[var(--color-canvas)] px-3.5 py-2.5">
          <span className="font-mono text-[11px] font-bold tracking-widest uppercase text-[var(--color-ink)]">
            {String(stopIndex + 1).padStart(2, '0')} // {(activeStop?.name ?? '').toUpperCase()}
          </span>
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close dossier"
            className="flex h-6 w-6 cursor-pointer items-center justify-center rounded text-[var(--color-ink-tertiary)] transition-colors hover:bg-[var(--color-surface-subtle)] hover:text-[var(--color-ink)]"
          >
            <X size={14} aria-hidden="true" />
          </button>
        </div>

        {/* Body: Lightweight headline-only list with inline accordion unfold */}
        <div className="min-h-0 flex-1 overflow-y-auto divide-y divide-[var(--color-line-subtle)] px-2 py-1">
          {/* Research Citations */}
          {stopCitations.map((c) => {
            const isExpanded = expandedId === c.id;
            return (
              <div key={c.id} className="py-1">
                <button
                  type="button"
                  onClick={() => toggleItem(c.id)}
                  aria-expanded={isExpanded}
                  className="flex w-full cursor-pointer items-start justify-between gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-[var(--color-surface-subtle)]"
                >
                  <div className="min-w-0 flex-1">
                    <div className="mb-0.5 flex items-center gap-1.5">
                      <span className="font-mono text-[8.5px] font-bold uppercase tracking-wider text-[var(--color-ink-tertiary)]">
                        {TYPE_LABELS[c.type] ?? c.type.toUpperCase()}
                      </span>
                      {c.year && (
                        <span className="font-mono text-[8.5px] text-[var(--color-ink-tertiary)]">
                          · {c.year}
                        </span>
                      )}
                    </div>
                    <div className="text-[12.5px] font-medium leading-snug text-[var(--color-ink)]">
                      {c.title}
                    </div>
                  </div>
                  <span className="mt-1 shrink-0 text-[var(--color-ink-tertiary)]">
                    {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                  </span>
                </button>

                {isExpanded && (
                  <div className="my-1.5 ml-2 border-l-2 border-[var(--color-line-strong)] pl-2.5 pr-2 text-[11.5px] leading-relaxed text-[var(--color-ink-secondary)]">
                    <p className="font-mono text-[10px] text-[var(--color-ink-tertiary)]">
                      {formatCitation(c)}
                    </p>
                    <p className="mt-1.5 text-[var(--color-ink)]">{c.takeaway}</p>
                    <p className="mt-1.5 text-[var(--color-ink-secondary)]">{c.howHalbertApplies}</p>
                    {c.url && (
                      <div className="mt-2">
                        <a
                          href={c.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 font-mono text-[10px] text-[var(--color-ink)] underline decoration-[var(--color-line-strong)] hover:text-[var(--color-stroke)]"
                        >
                          <span>Original work</span>
                          <ExternalLink size={10} aria-hidden="true" />
                        </a>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {/* Curated Shipped Features */}
          {stopFeatures.map((f) => {
            const isExpanded = expandedId === f.id;
            return (
              <div key={f.id} className="py-1">
                <button
                  type="button"
                  onClick={() => toggleItem(f.id)}
                  aria-expanded={isExpanded}
                  className="flex w-full cursor-pointer items-start justify-between gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-[var(--color-surface-subtle)]"
                >
                  <div className="min-w-0 flex-1">
                    <div className="mb-0.5 flex items-center gap-1.5">
                      <span className="font-mono text-[8.5px] font-bold uppercase tracking-wider text-[var(--color-stroke)]">
                        FEATURE
                      </span>
                      {f.category && (
                        <span className="font-mono text-[8.5px] text-[var(--color-ink-tertiary)] truncate">
                          · {f.category}
                        </span>
                      )}
                    </div>
                    <div className="text-[12.5px] font-medium leading-snug text-[var(--color-ink)]">
                      {f.name}
                    </div>
                  </div>
                  <span className="mt-1 shrink-0 text-[var(--color-ink-tertiary)]">
                    {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                  </span>
                </button>

                {isExpanded && (
                  <div className="my-1.5 ml-2 border-l-2 border-[var(--color-stroke)] pl-2.5 pr-2 text-[11.5px] leading-relaxed text-[var(--color-ink-secondary)]">
                    <p className="font-medium text-[var(--color-ink)]">{f.oneLine}</p>
                    <p className="mt-1.5 text-[var(--color-ink-secondary)]">{f.howItWorks}</p>
                    {f.toolingAndBackend && (
                      <p className="mt-1.5 font-mono text-[9.5px] text-[var(--color-ink-tertiary)]">
                        Source: {f.toolingAndBackend}
                      </p>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {stopCitations.length === 0 && stopFeatures.length === 0 && (
            <p className="px-3 py-6 text-center font-mono text-[11px] text-[var(--color-ink-tertiary)]">
              No entries for this stop.
            </p>
          )}
        </div>
      </div>
    </>
  );
}

export default TechnicalDossierModal;
