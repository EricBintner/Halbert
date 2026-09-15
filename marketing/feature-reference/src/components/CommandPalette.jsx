import React, { useEffect, useRef } from 'react';
import { Search, X, CornerDownLeft, BookOpen } from 'lucide-react';
import { StatusIndicator } from './StatusIndicator';

export function CommandPalette({
  isOpen,
  onClose,
  features,
  citations,
  featuresByCitationId,
  onSelectFeature,
}) {
  const [query, setQuery] = React.useState('');
  const inputRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      setQuery('');
    }
  }, [isOpen]);

  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const q = query.trim().toLowerCase();

  const featureMatches = (f) => {
    return (
      f.name.toLowerCase().includes(q) ||
      f.oneLine?.toLowerCase().includes(q) ||
      f.category?.toLowerCase().includes(q) ||
      f.toolingAndBackend?.toLowerCase().includes(q) ||
      f.scope?.some((s) => s.toLowerCase().includes(q))
    );
  };

  const citationMatches = (c) => {
    return (
      c.title.toLowerCase().includes(q) ||
      c.authors?.toLowerCase().includes(q) ||
      c.identifier.toLowerCase().includes(q) ||
      c.venue?.toLowerCase().includes(q)
    );
  };

  // Derived reverse join (plan §5.2): a citation row resolves to the first
  // feature whose citationIds include the citation, among ALL features on
  // this site — this is the reference dictionary, hidden/deferred stay
  // visible per the site's existing behaviour.
  const resolveFirstFeature = (citationId) => {
    const featureIds = featuresByCitationId?.[citationId] || [];
    return featureIds.length > 0 ? features.find((f) => f.id === featureIds[0]) : null;
  };

  let filteredFeatures = [];
  let filteredCitations = [];

  if (q) {
    filteredFeatures = features.filter(featureMatches);
    filteredCitations = (citations || []).filter(citationMatches);
  } else {
    filteredFeatures = features.slice(0, 8);
  }

  const totalResults = filteredFeatures.length + filteredCitations.length;

  const jumpToFeature = (featureId) => {
    onSelectFeature(featureId);
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-16 sm:pt-24 px-4 bg-black/40 backdrop-blur-sm select-none"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl rounded-xl border border-[var(--color-line)] bg-[var(--color-surface)] shadow-[var(--shadow-plate)] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search Input Bar */}
        <div className="flex items-center px-4 py-3.5 border-b border-[var(--color-line)]">
          <Search className="w-4 h-4 text-[var(--color-accent)] mr-3 shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search features, citations, RFCs, or code paths..."
            className="w-full bg-transparent text-sm font-sans text-[var(--color-ink)] placeholder-[var(--color-ink-tertiary)] focus:outline-none"
          />
          <button
            onClick={onClose}
            className="text-[var(--color-ink-tertiary)] hover:text-[var(--color-ink)] p-1 ml-2"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Results List */}
        <div className="max-h-[60vh] overflow-y-auto p-2 divide-y divide-[var(--color-line-subtle)]">
          {totalResults > 0 ? (
            <>
              {filteredFeatures.map((feature) => (
                <div
                  key={`feature-${feature.id}`}
                  onClick={() => jumpToFeature(feature.id)}
                  className="p-3.5 rounded-lg hover:bg-[var(--color-surface-subtle)] cursor-pointer transition-colors flex items-start justify-between gap-4 group"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center space-x-2 mb-1">
                      <span className="text-[10px] font-mono text-[var(--color-accent)] font-semibold uppercase tracking-wider">
                        {feature.category}
                      </span>
                      <span className="text-[var(--color-line)]">·</span>
                      <span className="font-display font-semibold text-sm text-[var(--color-ink)] group-hover:text-[var(--color-accent)] transition-colors">
                        {feature.name}
                      </span>
                    </div>
                    <p className="text-xs text-[var(--color-ink-secondary)] truncate font-sans">
                      {feature.oneLine}
                    </p>
                  </div>
                  <div className="shrink-0 flex items-center space-x-2">
                    <StatusIndicator status={feature.status} showDot={false} />
                    <CornerDownLeft className="w-3.5 h-3.5 text-[var(--color-ink-tertiary)] opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                </div>
              ))}

              {filteredCitations.map((citation) => {
                const firstFeature = resolveFirstFeature(citation.id);
                return (
                  <div
                    key={`citation-${citation.id}`}
                    onClick={() => {
                      if (firstFeature) jumpToFeature(firstFeature.id);
                    }}
                    className={`p-3.5 rounded-lg transition-colors flex items-start justify-between gap-4 group ${
                      firstFeature
                        ? 'hover:bg-[var(--color-surface-subtle)] cursor-pointer'
                        : 'opacity-70'
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center space-x-2 mb-1">
                        <BookOpen
                          className="w-3 h-3 text-[var(--color-accent)] shrink-0"
                          aria-hidden="true"
                        />
                        <span className="text-[10px] font-mono text-[var(--color-accent)] font-semibold uppercase tracking-wider">
                          RESEARCH
                        </span>
                        <span className="text-[var(--color-line)]">·</span>
                        <span className="font-display font-semibold text-sm text-[var(--color-ink)] group-hover:text-[var(--color-accent)] transition-colors truncate">
                          {citation.title}
                        </span>
                      </div>
                      <p className="text-xs text-[var(--color-ink-secondary)] truncate font-sans">
                        {firstFeature
                          ? `Cited by ${firstFeature.name}`
                          : `${citation.authors} · ${citation.identifier}`}
                      </p>
                    </div>
                    <div className="shrink-0 flex items-center space-x-2">
                      <span className="text-[10px] font-mono text-[var(--color-ink-tertiary)] uppercase tracking-wider shrink-0">
                        {citation.identifier}
                      </span>
                      {firstFeature && (
                        <CornerDownLeft className="w-3.5 h-3.5 text-[var(--color-ink-tertiary)] opacity-0 group-hover:opacity-100 transition-opacity" />
                      )}
                    </div>
                  </div>
                );
              })}
            </>
          ) : (
            <div className="py-12 text-center text-xs font-mono text-[var(--color-ink-tertiary)]">
              No matching specifications found for "{query}".
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-4 py-2.5 bg-[var(--color-surface-subtle)] border-t border-[var(--color-line)] text-[10px] font-mono text-[var(--color-ink-tertiary)] flex justify-between items-center">
          <span>NAVIGATION SHORTCUTS</span>
          <div className="flex items-center space-x-3">
            <span>[ESC] TO CLOSE</span>
            <span>[ENTER] TO JUMP</span>
          </div>
        </div>
      </div>
    </div>
  );
}