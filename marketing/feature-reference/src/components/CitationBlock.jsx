import React from 'react';
import { ArrowUpRight, Check } from 'lucide-react';

// Badge labels derive from the citation `type`, so an engineering report is
// never badged as a paper (plan §4.2, rev-2 finding 2).
const TYPE_LABELS = {
  paper: 'Paper',
  rfc: 'RFC',
  spec: 'Spec',
  benchmark: 'Benchmark',
  survey: 'Survey',
  'engineering-report': 'Eng. Report',
  licence: 'Licence',
};

// The application line is labelled by the measured `applied` status, never a
// uniform "applies this" (plan §4.2): shipped mechanisms cite the file, design
// influences state that they shape the architecture, deferred ones state the
// disposition. Third person, academic register.
const APPLIED_LABELS = {
  shipped: 'Grounds a shipped mechanism',
  design: 'Grounds the architecture — design influence',
  deferred: 'Disposition — deferred',
};

export function CitationBlock({ citation }) {
  const typeLabel = TYPE_LABELS[citation.type] || citation.type;
  const appliedLabel = APPLIED_LABELS[citation.applied] || 'Engineering application';
  const citationLine = [citation.authors, citation.venue, citation.identifier]
    .filter(Boolean)
    .join(' · ');

  return (
    <div className="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-subtle)] p-4 sm:p-5">
      {/* Type badge and honest peer-review mark */}
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <span className="text-[10px] font-mono font-semibold uppercase tracking-wider text-[var(--color-ink-secondary)] border border-[var(--color-line)] bg-[var(--color-surface)] px-1.5 py-0.5 rounded-sm">
          {typeLabel}
        </span>
        {citation.peerReviewed && (
          <span className="inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider text-[var(--color-ink-tertiary)]">
            <Check
              className="w-3 h-3 text-[var(--color-status-nominal)]"
              aria-hidden="true"
            />
            Peer-Reviewed
          </span>
        )}
      </div>

      {/* Title as external link */}
      <a
        href={citation.url}
        target="_blank"
        rel="noreferrer"
        className="group inline-flex items-start gap-1.5 font-display font-medium text-[15px] sm:text-base text-[var(--color-ink)] hover:text-[var(--color-accent)] transition-colors leading-snug"
      >
        <span>{citation.title}</span>
        <ArrowUpRight
          className="w-3.5 h-3.5 shrink-0 mt-0.5 text-[var(--color-ink-tertiary)] group-hover:text-[var(--color-accent)] transition-colors"
          aria-hidden="true"
        />
      </a>

      {/* Monospace citation line */}
      <div className="mt-1.5 text-[11px] font-mono text-[var(--color-ink-tertiary)] leading-relaxed">
        {citationLine}
      </div>

      {/* Takeaway: the theoretical finding */}
      <p className="mt-2.5 text-xs text-[var(--color-ink-secondary)] font-sans leading-relaxed">
        {citation.takeaway}
      </p>

      {/* Engineering application, labelled by the measured applied status */}
      <div className="mt-3 pt-3 border-t border-[var(--color-line-subtle)]">
        <span className="block font-mono uppercase tracking-wider text-[10px] text-[var(--color-ink-tertiary)] font-semibold mb-1">
          {appliedLabel}
        </span>
        <p className="text-xs text-[var(--color-ink)] font-sans leading-relaxed">
          {citation.howHalbertApplies}
        </p>
      </div>
    </div>
  );
}