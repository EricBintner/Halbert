import React, { useEffect, useMemo, useRef, useState } from 'react';
import { BookOpen, X, ChevronRight, ExternalLink } from 'lucide-react';
import { STOPS } from '../lib/storyboard';
import {
  citationsForStop,
  featuresForStop,
  formatCitation,
} from '../lib/researchData';

/**
 * TechnicalDossierModal — ultra-minimal stop-curated research dossier.
 *
 * Triggered by a standalone graphic icon in the lower-left corner that
 * hides when the dossier is open. On desktop, the panel maintains a
 * fixed, constant height (never jumps when selecting items) and list
 * items are condensed to single lines. Selecting an item expands an
 * attached right fly-out detail pane of the exact same height with
 * isolated, smooth internal scrolling that never leaks to the parallax.
 * On mobile, renders a clean full-window sheet with inline expansion.
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
  const [selectedId, setSelectedId] = useState(null);

  const reducedMotion = usePrefersReducedMotion();
  const triggerRef = useRef(null);
  const panelRef = useRef(null);
  useFocusTrap(open, panelRef);

  // Esc closes either the active detail fly-out or the whole popup
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') {
        if (selectedId) {
          setSelectedId(null);
        } else {
          setOpen(false);
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, selectedId]);

  // Prevent wheel events inside the modal from leaking to window and scrolling the parallax
  useEffect(() => {
    const panel = panelRef.current;
    if (!panel || !open) return undefined;

    const onWheel = (e) => {
      // Find the scrollable container under the cursor
      const scrollable = e.target.closest('.overflow-y-auto');
      if (!scrollable) {
        // If not directly over a scrollable area (e.g. header, borders), isolate window from wheel
        e.preventDefault();
        return;
      }

      // If over a scrollable container, allow smooth native scrolling within bounds,
      // but prevent window scroll chaining when hitting top or bottom edges
      const { scrollTop, scrollHeight, clientHeight } = scrollable;
      const isAtTop = scrollTop <= 0 && e.deltaY < 0;
      const isAtBottom = scrollTop + clientHeight >= scrollHeight - 1 && e.deltaY > 0;

      if (isAtTop || isAtBottom) {
        e.preventDefault();
      }
    };

    panel.addEventListener('wheel', onWheel, { passive: false });
    return () => panel.removeEventListener('wheel', onWheel);
  }, [open]);

  // Focus management
  const prevOpen = useRef(false);
  useEffect(() => {
    if (prevOpen.current === open) return;
    if (open) {
      if (panelRef.current) panelRef.current.focus();
    } else {
      setSelectedId(null);
      if (triggerRef.current) triggerRef.current.focus();
    }
    prevOpen.current = open;
  }, [open]);

  // Reset selected item on stop change so view stays lightweight
  useEffect(() => {
    setSelectedId(null);
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

  // Unified items list
  const items = useMemo(() => {
    const citationItems = stopCitations.map((c) => ({
      id: c.id,
      kind: 'citation',
      typeLabel: TYPE_LABELS[c.type] ?? c.type.toUpperCase(),
      title: c.title,
      meta: c.year ? `${c.authors} · ${c.year}` : c.authors,
      fullCitation: formatCitation(c),
      takeaway: c.takeaway,
      howHalbertApplies: c.howHalbertApplies,
      url: c.url,
    }));

    const featureItems = stopFeatures.map((f) => ({
      id: f.id,
      kind: 'feature',
      typeLabel: 'FEATURE',
      title: f.name,
      meta: f.category,
      takeaway: f.oneLine,
      howHalbertApplies: f.howItWorks,
      toolingAndBackend: f.toolingAndBackend,
    }));

    return [...citationItems, ...featureItems];
  }, [stopCitations, stopFeatures]);

  const selectedItem = useMemo(() => {
    return items.find((i) => i.id === selectedId) ?? null;
  }, [items, selectedId]);

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
      {/* Standalone Graphic Icon Trigger — hides when popup is open */}
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen(true)}
        aria-expanded={open}
        aria-controls={PANEL_ID}
        aria-haspopup="dialog"
        aria-label="Research & Architecture Dossier"
        data-testid="dossier-trigger"
        style={{
          bottom: 'calc(env(safe-area-inset-bottom, 0px) + 1rem)',
          left: 'calc(env(safe-area-inset-left, 0px) + 1rem)',
        }}
        className={`fixed z-40 flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)]/95 text-[var(--color-ink)] shadow-[var(--shadow-plate)] backdrop-blur-md transition-all duration-200 hover:border-[var(--color-stroke)] hover:text-[var(--color-stroke)] active:scale-95 cursor-pointer ${
          open ? 'opacity-0 pointer-events-none scale-75' : 'opacity-100 scale-100'
        }`}
      >
        <BookOpen size={16} aria-hidden="true" />
      </button>

      {/* Popup Dialog — fixed constant height on desktop with fly-out detail pane */}
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
        style={{
          ...panelStyle,
          overscrollBehavior: 'contain',
        }}
        className={`fixed z-50 flex items-stretch rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)]/95 text-[var(--color-ink)] shadow-[var(--shadow-popover)] backdrop-blur-xl origin-bottom-left max-sm:inset-0 max-sm:rounded-none max-sm:flex-col max-sm:h-full sm:bottom-4 sm:left-4 sm:h-[285px] sm:origin-bottom-left ${openClass}`}
      >
        {/* Left Pane: Single-line item list (fixed compact height) */}
        <div className="flex flex-col w-full sm:w-[320px] shrink-0 h-full min-h-0">
          {/* Header */}
          <div className="flex shrink-0 items-center justify-between border-b border-[var(--color-line)] bg-[var(--color-canvas)] px-3 py-2">
            <span className="font-mono text-[10.5px] font-bold tracking-widest uppercase text-[var(--color-ink)] truncate">
              {String(stopIndex + 1).padStart(2, '0')} // {(activeStop?.name ?? '').toUpperCase()}
            </span>
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                setSelectedId(null);
              }}
              aria-label="Close dossier"
              className="flex h-5 w-5 shrink-0 cursor-pointer items-center justify-center rounded text-[var(--color-ink-tertiary)] transition-colors hover:bg-[var(--color-surface-subtle)] hover:text-[var(--color-ink)] ml-2"
            >
              <X size={13} aria-hidden="true" />
            </button>
          </div>

          {/* List of single-line rows — scrollable with overscroll-contain */}
          <div
            className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-1.5 space-y-0.5"
            style={{ overscrollBehavior: 'contain' }}
          >
            {items.map((item) => {
              const isSelected = selectedId === item.id;
              return (
                <div key={item.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(isSelected ? null : item.id)}
                    aria-expanded={isSelected}
                    className={`group flex w-full items-center gap-1.5 px-2 py-1 rounded text-left transition-colors cursor-pointer ${
                      isSelected
                        ? 'bg-[var(--color-surface-subtle)] text-[var(--color-ink)] border-l-2 border-[var(--color-stroke)]'
                        : 'hover:bg-[var(--color-surface-subtle)]/70 text-[var(--color-ink)]'
                    }`}
                  >
                    <span
                      className={`shrink-0 font-mono text-[8px] font-bold uppercase tracking-wider px-1 py-0.5 rounded-xs border ${
                        item.kind === 'feature'
                          ? 'border-[var(--color-stroke)] text-[var(--color-stroke)]'
                          : 'border-[var(--color-line-strong)] text-[var(--color-ink-tertiary)]'
                      }`}
                    >
                      {item.typeLabel}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-[11.5px] font-medium leading-tight">
                      {item.title}
                    </span>
                    <ChevronRight
                      size={12}
                      className={`shrink-0 text-[var(--color-ink-tertiary)] group-hover:text-[var(--color-ink)] transition-transform ${
                        isSelected ? 'rotate-90 sm:rotate-0 text-[var(--color-stroke)]' : ''
                      }`}
                    />
                  </button>

                  {/* Mobile-only inline expansion (accordion fallback) */}
                  {isSelected && (
                    <div className="sm:hidden my-1.5 ml-2 border-l-2 border-[var(--color-stroke)] pl-2.5 pr-2 py-1 text-[11.5px] leading-relaxed text-[var(--color-ink-secondary)] bg-[var(--color-surface-subtle)]/50 rounded-r">
                      {item.fullCitation && (
                        <p className="font-mono text-[9.5px] text-[var(--color-ink-tertiary)]">
                          {item.fullCitation}
                        </p>
                      )}
                      <p className="mt-1 text-[var(--color-ink)]">{item.takeaway}</p>
                      {item.howHalbertApplies && (
                        <p className="mt-1 text-[var(--color-ink-secondary)]">{item.howHalbertApplies}</p>
                      )}
                      {item.toolingAndBackend && (
                        <p className="mt-1 font-mono text-[9px] text-[var(--color-ink-tertiary)]">
                          Source: {item.toolingAndBackend}
                        </p>
                      )}
                      {item.url && (
                        <div className="mt-1.5">
                          <a
                            href={item.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 font-mono text-[10px] text-[var(--color-ink)] underline decoration-[var(--color-line-strong)] hover:text-[var(--color-stroke)]"
                          >
                            <span>Original work</span>
                            <ExternalLink size={9} aria-hidden="true" />
                          </a>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}

            {items.length === 0 && (
              <p className="px-2 py-4 text-center font-mono text-[10.5px] text-[var(--color-ink-tertiary)]">
                No entries for this stop.
              </p>
            )}
          </div>
        </div>

        {/* Right Pane (Desktop Fly-Out): exact same locked height as left pane, headerless, fully scrollable */}
        <div
          className={`hidden sm:flex flex-col h-full min-h-0 border-l border-[var(--color-line)] bg-[var(--color-canvas)] transition-all duration-200 ease-out overflow-hidden ${
            selectedItem ? 'w-[360px] opacity-100' : 'w-0 opacity-0 pointer-events-none'
          }`}
        >
          {selectedItem && (
            /* Detail Body — takes full panel height without a duplicate header or close button */
            <div
              tabIndex={0}
              className="h-full overflow-y-auto overscroll-contain p-3.5 text-[11.5px] leading-relaxed text-[var(--color-ink-secondary)] space-y-2 focus:outline-none"
              style={{ overscrollBehavior: 'contain' }}
            >
              <div className="flex items-center gap-1.5 font-mono text-[9px] font-bold uppercase tracking-wider text-[var(--color-ink-tertiary)]">
                <span>{selectedItem.typeLabel}</span>
                {selectedItem.meta && <span>· {selectedItem.meta}</span>}
              </div>

              <h4 className="text-[13px] font-semibold leading-snug text-[var(--color-ink)]">
                {selectedItem.title}
              </h4>

              {selectedItem.fullCitation && (
                <p className="font-mono text-[9.5px] text-[var(--color-ink-tertiary)] leading-normal">
                  {selectedItem.fullCitation}
                </p>
              )}

              <p className="text-[var(--color-ink)] leading-normal">
                {selectedItem.takeaway}
              </p>

              {selectedItem.howHalbertApplies && (
                <div className="border-l-2 border-[var(--color-stroke)] pl-2 pt-0.5 text-[var(--color-ink-secondary)]">
                  <span className="font-mono text-[8.5px] font-bold uppercase tracking-wider block text-[var(--color-stroke)] mb-0.5">
                    In Halbert
                  </span>
                  {selectedItem.howHalbertApplies}
                </div>
              )}

              {selectedItem.toolingAndBackend && (
                <p className="font-mono text-[9px] text-[var(--color-ink-tertiary)]">
                  Source: {selectedItem.toolingAndBackend}
                </p>
              )}

              {selectedItem.url && (
                <div className="pt-1">
                  <a
                    href={selectedItem.url}
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
      </div>
    </>
  );
}

export default TechnicalDossierModal;
