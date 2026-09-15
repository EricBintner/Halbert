import React, { useEffect, useMemo, useRef, useState } from 'react';
import { X, ChevronLeft, ChevronRight, Search } from 'lucide-react';
import { STOPS } from '../lib/storyboard';
import {
  CITATIONS,
  SHIPPED_FEATURES,
  citationsForStop,
  featuresForStop,
  featuresForCitation,
  formatCitation,
} from '../lib/researchData';

/**
 * TechnicalDossierModal — the marketing site's research dossier.
 *
 * A corner trigger (bottom-left) opens a panel that tracks the active
 * storyboard stop: research citations and catalog features anchored to
 * the on-screen stop, the full searchable bibliography, and the cited
 * shipped features grouped by category. Voice is third person,
 * academic register (founder ruling 2026-09-15) — this is a reference
 * layer, not a conversation.
 *
 * Every count shown derives from the JSON at render (plan §4.2: a
 * typed count is a stale claim waiting to happen). Colours come only
 * from the token vars. No emoji anywhere in this surface.
 *
 * The panel stays mounted and switches on `inert` when closed, so the
 * open transition runs from real starting styles instead of a mount —
 * and `prefers-reduced-motion` collapses it through the duration token
 * (`--duration-shutter` is 0ms there), with no animation at all when
 * the OS gate is on.
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

// Third-person, per-status labels (plan §4.2): shipped prose names the
// mechanism and file; design prose says it shaped the architecture;
// deferred prose states the disposition. Never a uniform "applies this".
const APPLIED = {
  shipped: { label: 'HOW HALBERT SHIPS IT', tone: 'var(--color-status-nominal)' },
  design: { label: 'HOW IT SHAPED THE DESIGN', tone: 'var(--color-status-telemetry)' },
  deferred: { label: 'DISPOSITION IN HALBERT', tone: 'var(--color-status-warning)' },
};

const PAD2 = (n) => String(n).padStart(2, '0');

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

/** Traps Tab focus inside the panel while it is open. */
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

function matchCitation(c, q) {
  if (!q) return true;
  const hay = [c.title, c.authors, c.venue, c.identifier, c.takeaway, c.type].join(' ').toLowerCase();
  return hay.includes(q);
}

function matchFeature(f, q) {
  if (!q) return true;
  const hay = [f.name, f.oneLine, f.howItWorks, f.whatItIs, f.toolingAndBackend].join(' ').toLowerCase();
  return hay.includes(q);
}

function TypeBadge({ type, peerReviewed }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="inline-flex items-center rounded-sm border border-[var(--color-line)] bg-[var(--color-surface-subtle)] px-1.5 py-0.5 font-mono text-[9px] font-bold tracking-wider text-[var(--color-ink-secondary)]">
        {TYPE_LABELS[type] ?? type.toUpperCase()}
      </span>
      {peerReviewed && (
        <span
          className="inline-flex items-center rounded-sm border border-[var(--color-status-nominal-line)] bg-[var(--color-status-nominal-bg)] px-1.5 py-0.5 font-mono text-[9px] font-bold tracking-wider text-[var(--color-status-nominal)]"
          title="Peer-reviewed"
        >
          PEER-REVIEWED
        </span>
      )}
    </span>
  );
}

function StatusPill({ status }) {
  return (
    <span className="inline-flex items-center rounded-full border border-[var(--color-line)] bg-[var(--color-surface-subtle)] px-2 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider text-[var(--color-ink-secondary)]">
      {status}
    </span>
  );
}

function FeatureChip({ feature }) {
  return (
    <span className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-[var(--color-line)] bg-[var(--color-surface)] px-1.5 py-0.5">
      <span className="truncate text-[10px] font-medium text-[var(--color-ink)]">{feature.name}</span>
      <StatusPill status={feature.status} />
    </span>
  );
}

function CitationCard({ citation }) {
  const applied = APPLIED[citation.applied] ?? APPLIED.design;
  const related = featuresForCitation(citation.id);
  return (
    <article className="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)] p-3.5">
      <div className="flex flex-wrap items-center gap-2">
        <TypeBadge type={citation.type} peerReviewed={citation.peerReviewed} />
        <span className="font-mono text-[10px] tracking-wider text-[var(--color-ink-tertiary)]">
          {citation.year}
        </span>
      </div>
      <h3 className="mt-2 text-[15px] font-semibold leading-snug">
        <a
          href={citation.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[var(--color-ink)] underline decoration-[var(--color-line-strong)] decoration-1 underline-offset-2 transition-colors hover:decoration-[var(--color-stroke)]"
        >
          {citation.title}
          <span className="ml-1 text-[var(--color-ink-secondary)]" aria-hidden="true">↗</span>
        </a>
      </h3>
      <p className="mt-1.5 font-mono text-[10.5px] leading-relaxed text-[var(--color-ink-secondary)]">
        {formatCitation(citation)}
      </p>
      <p className="mt-2 text-[12.5px] leading-relaxed text-[var(--color-ink)]">{citation.takeaway}</p>
      <div
        className="mt-3 rounded-md border-l-2 bg-[var(--color-surface-subtle)] p-2.5"
        style={{ borderLeftColor: applied.tone }}
      >
        <div className="font-mono text-[9px] font-bold uppercase tracking-widest" style={{ color: applied.tone }}>
          {applied.label}
        </div>
        <p className="mt-1 text-[12px] leading-relaxed text-[var(--color-ink)]">{citation.howHalbertApplies}</p>
      </div>
      {citation.applied === 'shipped' && related.length > 0 && (
        <div className="mt-3">
          <div className="font-mono text-[9px] font-bold uppercase tracking-widest text-[var(--color-ink-tertiary)]">
            In the shipped architecture
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {related.map((f) => (
              <FeatureChip key={f.id} feature={f} />
            ))}
          </div>
        </div>
      )}
    </article>
  );
}

function FeatureCard({ feature }) {
  const cited =
    Array.isArray(feature.citationIds) && feature.citationIds.length > 0
      ? feature.citationIds
          .map((id) => CITATIONS.find((c) => c.id === id))
          .filter(Boolean)
      : [];
  return (
    <article className="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)] p-3.5">
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill status={feature.status} />
        <span className="font-mono text-[9px] uppercase tracking-widest text-[var(--color-ink-tertiary)]">
          {feature.category}
        </span>
      </div>
      <h3 className="mt-2 text-[15px] font-semibold leading-snug text-[var(--color-ink)]">{feature.name}</h3>
      <p className="mt-1 text-[12.5px] leading-relaxed text-[var(--color-ink-secondary)]">{feature.oneLine}</p>
      <p className="mt-2 text-[12px] leading-relaxed text-[var(--color-ink)]">{feature.howItWorks}</p>
      {feature.toolingAndBackend && (
        <p className="mt-2 font-mono text-[10px] leading-relaxed text-[var(--color-ink-tertiary)]">
          {feature.toolingAndBackend}
        </p>
      )}
      {cited.length > 0 && (
        <div className="mt-3 border-t border-[var(--color-line-subtle)] pt-2.5">
          <div className="font-mono text-[9px] font-bold uppercase tracking-widest text-[var(--color-ink-tertiary)]">
            Cited by
          </div>
          <ul className="mt-1 space-y-0.5">
            {cited.map((c) => (
              <li key={c.id} className="text-[11px] leading-snug text-[var(--color-ink-secondary)]">
                {c.title} ({c.year})
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}

function EmptyState({ children }) {
  return (
    <p className="px-1 py-6 text-center font-mono text-[11px] tracking-wider text-[var(--color-ink-tertiary)]">
      {children}
    </p>
  );
}

const PANEL_ID = 'technical-dossier-panel';

export function TechnicalDossierModal({ camera, stops, onSelectStop }) {
  const stopIndex = camera?.stopIndex ?? 0;
  const allStops = stops ?? STOPS;
  const activeStop = allStops[stopIndex] ?? allStops[0];
  const activeStopId = activeStop?.id ?? '';

  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState('focus');
  const [query, setQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState(null);

  const reducedMotion = usePrefersReducedMotion();
  const triggerRef = useRef(null);
  const panelRef = useRef(null);
  useFocusTrap(open, panelRef);

  // Esc closes. A stale query or category chip would filter the next
  // opening, so both reset with the panel. On close, focus returns to
  // the trigger (the trigger keeps page focus; the panel is inert
  // while closed, so it never steals Tab or arrow keys between uses).
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const prevOpen = useRef(false);
  useEffect(() => {
    if (prevOpen.current === open) return;
    if (open) {
      // Enter the dialog: settle focus onto the panel itself so Tab
      // starts inside it, not behind it.
      if (panelRef.current) panelRef.current.focus();
    } else {
      setQuery('');
      setCategoryFilter(null);
      if (triggerRef.current) triggerRef.current.focus();
    }
    prevOpen.current = open;
  }, [open]);

  const stopCitations = useMemo(() => citationsForStop(activeStopId), [activeStopId]);
  const stopFeatures = useMemo(() => featuresForStop(activeStopId), [activeStopId]);

  // Architecture Catalog: shipped features that cite at least one entry.
  const citedShippedFeatures = useMemo(
    () => SHIPPED_FEATURES.filter((f) => Array.isArray(f.citationIds) && f.citationIds.length > 0),
    [],
  );

  const q = query.trim().toLowerCase();

  const allResearch = useMemo(
    () => CITATIONS.filter((c) => matchCitation(c, q) && (!categoryFilter || c.category === categoryFilter)),
    [q, categoryFilter],
  );

  const catalogFeatures = useMemo(
    () => citedShippedFeatures.filter((f) => matchFeature(f, q)),
    [citedShippedFeatures, q],
  );

  const catalogByCategory = useMemo(() => {
    const groups = new Map();
    for (const f of catalogFeatures) {
      const key = f.category ?? '';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(f);
    }
    return groups;
  }, [catalogFeatures]);

  const focusCitations = tab === 'focus' && q ? stopCitations.filter((c) => matchCitation(c, q)) : stopCitations;
  const focusFeatures = tab === 'focus' && q ? stopFeatures.filter((f) => matchFeature(f, q)) : stopFeatures;

  const citationCategories = useMemo(() => {
    const counts = new Map();
    for (const c of CITATIONS) counts.set(c.category, (counts.get(c.category) ?? 0) + 1);
    return counts;
  }, []);

  const jump = (delta) => {
    const next = (stopIndex + delta + allStops.length) % allStops.length;
    if (onSelectStop) onSelectStop(next);
  };

  // Scale-in from the bottom-left corner. The visibility transition is
  // deliberately two-sided: reading from the AFTER-change style, opening
  // flips to visible instantly (the scale-in is visible from frame one)
  // while closing holds visibility for the fade, then hides. Reduced
  // motion drops the transition and transform entirely — and the
  // OS-level gate zeroes the shutter tokens anyway, so either path
  // gives that user an instant open from one code path.
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
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={PANEL_ID}
        aria-haspopup="dialog"
        data-testid="dossier-trigger"
        data-stop-index={stopIndex}
        style={{ paddingBottom: 'calc(env(safe-area-inset-bottom, 0px) + 0.25rem)' }}
        className="group fixed bottom-6 left-6 z-40 flex items-center gap-2.5 rounded-full border border-[var(--color-line)] bg-[var(--color-surface)] py-2 pl-3 pr-4 shadow-[var(--shadow-plate)] transition-transform duration-150 hover:-translate-y-0.5 active:translate-y-0 cursor-pointer"
      >
        <span
          className="h-2 w-2 shrink-0 rounded-full bg-[var(--color-stroke)] transition-transform duration-150 group-hover:scale-125"
          aria-hidden="true"
        />
        <span className="font-mono text-[10px] font-bold tracking-widest uppercase text-[var(--color-ink)]">
          Research &amp; Specs
        </span>
        <span className="font-mono text-[10px] tracking-wider text-[var(--color-ink-secondary)]">
          [{stopCitations.length} papers · {stopFeatures.length} features]
        </span>
      </button>

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
        className={`fixed inset-0 z-50 flex flex-col overflow-hidden rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)]/95 text-[var(--color-ink)] shadow-[var(--shadow-popover)] backdrop-blur-xl max-sm:rounded-none sm:inset-auto sm:bottom-20 sm:left-6 sm:w-[540px] sm:max-w-[calc(100vw-3rem)] sm:max-h-[82vh] sm:origin-bottom-left ${openClass}`}
      >
        {/* Header: stop selector, search, tabs, close. The phone sheet is
            fixed inset-0, so the notch insets come from env() here — a
            zero-inset display keeps the authored padding. */}
        <div
          className="shrink-0 border-b border-[var(--color-line)] bg-[var(--color-canvas)] px-3.5 pb-3 pt-3.5 max-sm:px-4 max-sm:pt-4"
          style={{
            paddingTop: 'calc(env(safe-area-inset-top, 0px) + 0.875rem)',
            paddingLeft: 'calc(env(safe-area-inset-left, 0px) + 1rem)',
            paddingRight: 'calc(env(safe-area-inset-right, 0px) + 1rem)',
          }}
        >
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => jump(-1)}
              aria-label="Previous stop"
              className="flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-md border border-[var(--color-line)] text-[var(--color-ink-secondary)] transition-colors hover:bg-[var(--color-surface-subtle)] hover:text-[var(--color-ink)]"
            >
              <ChevronLeft size={14} aria-hidden="true" />
            </button>
            <div className="min-w-0 flex-1 truncate text-center font-mono text-[11px] font-bold tracking-widest uppercase text-[var(--color-ink)]">
              Stop {PAD2(stopIndex + 1)} / {PAD2(allStops.length)} · {(activeStop?.name ?? '').toUpperCase()}
            </div>
            <button
              type="button"
              onClick={() => jump(1)}
              aria-label="Next stop"
              className="flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-md border border-[var(--color-line)] text-[var(--color-ink-secondary)] transition-colors hover:bg-[var(--color-surface-subtle)] hover:text-[var(--color-ink)]"
            >
              <ChevronRight size={14} aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close dossier"
              className="ml-1 flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-md border border-[var(--color-line)] text-[var(--color-ink-secondary)] transition-colors hover:bg-[var(--color-surface-subtle)] hover:text-[var(--color-ink)]"
            >
              <X size={14} aria-hidden="true" />
            </button>
          </div>

          <div className="mt-2.5 flex items-center gap-2 rounded-md border border-[var(--color-line)] bg-[var(--color-surface)] px-2.5 py-1.5">
            <Search size={13} className="shrink-0 text-[var(--color-ink-tertiary)]" aria-hidden="true" />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={`Filter ${CITATIONS.length} papers & ${citedShippedFeatures.length} features...`}
              aria-label="Filter research and features"
              className="w-full min-w-0 bg-transparent font-mono text-[11px] text-[var(--color-ink)] placeholder:text-[var(--color-ink-tertiary)] focus:outline-none"
            />
          </div>

          <div className="mt-2.5 grid grid-cols-3 gap-1.5" role="tablist" aria-label="Dossier sections">
            {[
              ['focus', 'Section Focus'],
              ['all', `All Research (${CITATIONS.length})`],
              ['catalog', `Architecture Catalog (${citedShippedFeatures.length})`],
            ].map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                onClick={() => setTab(id)}
                className={`cursor-pointer truncate rounded-md border px-2 py-1.5 font-mono text-[9.5px] font-bold tracking-wider uppercase transition-colors ${
                  tab === id
                    ? 'border-[var(--color-stroke)] bg-[var(--color-stroke)] text-[var(--color-ink-on-stroke)]'
                    : 'border-[var(--color-line)] text-[var(--color-ink-secondary)] hover:bg-[var(--color-surface-subtle)] hover:text-[var(--color-ink)]'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Body */}
        <div className="min-h-0 flex-1 overflow-y-auto px-3.5 py-3.5">
          {tab === 'focus' && (
            <div className="space-y-3">
              <p className="px-1 font-mono text-[10px] tracking-widest uppercase text-[var(--color-ink-tertiary)]">
                {(activeStop?.name ?? '')} · {focusCitations.length} citations · {focusFeatures.length} features
              </p>
              {focusCitations.map((c) => (
                <CitationCard key={c.id} citation={c} />
              ))}
              {focusFeatures.map((f) => (
                <FeatureCard key={f.id} feature={f} />
              ))}
              {focusCitations.length === 0 && focusFeatures.length === 0 && (
                <EmptyState>No matching entries for this stop.</EmptyState>
              )}
            </div>
          )}

          {tab === 'all' && (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-1.5 px-1">
                <button
                  type="button"
                  onClick={() => setCategoryFilter(null)}
                  className={`cursor-pointer rounded-full border px-2.5 py-1 font-mono text-[9.5px] font-bold tracking-wider uppercase transition-colors ${
                    categoryFilter === null
                      ? 'border-[var(--color-stroke)] text-[var(--color-stroke)]'
                      : 'border-[var(--color-line)] text-[var(--color-ink-secondary)] hover:text-[var(--color-ink)]'
                  }`}
                >
                  All ({CITATIONS.length})
                </button>
                {[...citationCategories.entries()].map(([cat, count]) => (
                  <button
                    key={cat}
                    type="button"
                    onClick={() => setCategoryFilter((cur) => (cur === cat ? null : cat))}
                    className={`cursor-pointer rounded-full border px-2.5 py-1 font-mono text-[9.5px] font-bold tracking-wider uppercase transition-colors ${
                      categoryFilter === cat
                        ? 'border-[var(--color-stroke)] text-[var(--color-stroke)]'
                        : 'border-[var(--color-line)] text-[var(--color-ink-secondary)] hover:text-[var(--color-ink)]'
                    }`}
                  >
                    {cat} ({count})
                  </button>
                ))}
              </div>
              {allResearch.length > 0 ? (
                allResearch.map((c) => <CitationCard key={c.id} citation={c} />)
              ) : (
                <EmptyState>No citations match that filter.</EmptyState>
              )}
            </div>
          )}

          {tab === 'catalog' && (
            <div className="space-y-4">
              {[...catalogByCategory.entries()].map(([category, features]) => (
                <section key={category}>
                  <h3 className="mb-2 px-1 font-mono text-[10px] font-bold tracking-widest uppercase text-[var(--color-ink-tertiary)]">
                    {category} ({features.length})
                  </h3>
                  <div className="space-y-3">
                    {features.map((f) => (
                      <FeatureCard key={f.id} feature={f} />
                    ))}
                  </div>
                </section>
              ))}
              {catalogFeatures.length === 0 && <EmptyState>No features match that filter.</EmptyState>}
            </div>
          )}
        </div>

        {/* Footer: canonical deployed reference + licence line */}
        <div
          className="shrink-0 border-t border-[var(--color-line)] bg-[var(--color-canvas)] px-3.5 py-2.5"
          style={{
            paddingBottom: 'calc(env(safe-area-inset-bottom, 0px) + 0.625rem)',
            paddingLeft: 'calc(env(safe-area-inset-left, 0px) + 0.875rem)',
            paddingRight: 'calc(env(safe-area-inset-right, 0px) + 0.875rem)',
          }}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <a
              href="https://halbert.computer/features/"
              target="_blank"
              rel="noopener noreferrer"
              className="font-mono text-[10.5px] font-bold tracking-wider uppercase text-[var(--color-ink)] underline decoration-[var(--color-line-strong)] decoration-1 underline-offset-2 transition-colors hover:decoration-[var(--color-stroke)]"
            >
              Open Full Architecture Dictionary →
            </a>
            <span className="font-mono text-[9.5px] tracking-wider uppercase text-[var(--color-ink-tertiary)]">
              Open Source · GPL-3.0 · Zero Cloud Telemetry
            </span>
          </div>
        </div>
      </div>
    </>
  );
}

export default TechnicalDossierModal;