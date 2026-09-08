import React, { useState } from 'react';
import { StatusIndicator } from './StatusIndicator';
import { ChevronDown, ChevronUp } from 'lucide-react';

function SubFeatureItem({ feature }) {
  return (
    <div className="pt-4 mt-4 border-t border-[var(--color-line-subtle)]" id={feature.id}>
      <div className="flex items-baseline justify-between gap-4 mb-1">
        <h4 className="font-display font-medium text-base text-[var(--color-ink)]">
          {feature.name}
        </h4>
        <StatusIndicator status={feature.status} />
      </div>

      {feature.oneLine && (
        <p className="text-xs text-[var(--color-ink-secondary)] mb-2 font-sans">
          {feature.oneLine}
        </p>
      )}

      {feature.whatItIs && (
        <p className="text-xs text-[var(--color-ink)] leading-relaxed font-sans mb-1.5">
          {feature.whatItIs}
        </p>
      )}

      {feature.toolingAndBackend && (
        <div className="text-[11px] font-mono text-[var(--color-ink-tertiary)] mt-2">
          Source: <span className="text-[var(--color-ink)]">{feature.toolingAndBackend}</span>
        </div>
      )}
    </div>
  );
}

export function FeatureDossier({ feature, forceOpen = false }) {
  const [expanded, setExpanded] = useState(false);
  const isExpanded = forceOpen || expanded;

  return (
    <article
      id={feature.id}
      className="scroll-mt-24 p-6 sm:p-8 rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)] transition-colors"
    >
      {/* Plate Header */}
      <div className="flex items-baseline justify-between gap-4 pb-3 border-b border-[var(--color-line-subtle)]">
        <div className="flex items-baseline space-x-3 min-w-0">
          <h3 className="font-display font-semibold text-2xl text-[var(--color-ink)] tracking-tight">
            {feature.name}
          </h3>
          <span className="text-xs font-mono text-[var(--color-ink-tertiary)] select-all">
            #{feature.id}
          </span>
        </div>
        <div className="shrink-0">
          <StatusIndicator status={feature.status} />
        </div>
      </div>

      {/* Premise & Lead */}
      {feature.oneLine && (
        <p className="mt-3 text-base text-[var(--color-ink-secondary)] font-sans leading-relaxed">
          {feature.oneLine}
        </p>
      )}

      {feature.gating && (
        <div className="mt-2 text-xs font-mono text-[var(--color-ink-tertiary)]">
          Requires: <span className="text-[var(--color-ink)]">{feature.gating}</span>
        </div>
      )}

      {/* Narrative Body: Clean, readable paragraphs without loud subheadings */}
      <div className="mt-5 space-y-3 font-sans text-sm sm:text-[15px] leading-relaxed">
        {feature.whatItIs && (
          <p className="text-[var(--color-ink)]">
            {feature.whatItIs}
          </p>
        )}

        {feature.howItWorks && (
          <p className="text-[var(--color-ink-secondary)]">
            {feature.howItWorks}
          </p>
        )}
      </div>

      {/* Invariants: quiet, intentional quote-style note */}
      {feature.limitsAndInvariants && (
        <div className="mt-5 pt-4 border-t border-[var(--color-line-subtle)] text-xs font-sans text-[var(--color-ink-secondary)]">
          <span className="font-mono uppercase tracking-wider text-[10px] text-[var(--color-ink-tertiary)] font-semibold block mb-1">
            Invariants & Guardrails
          </span>
          <p className="pl-3 border-l-2 border-[var(--color-line-strong)] leading-relaxed">
            {feature.limitsAndInvariants}
          </p>
        </div>
      )}

      {/* Technical Footprint: Sources and Citations */}
      {(feature.toolingAndBackend || feature.decisionRefs?.length > 0) && (
        <div className="mt-5 pt-4 border-t border-[var(--color-line-subtle)] flex flex-wrap items-baseline justify-between gap-y-2 text-xs font-mono text-[var(--color-ink-tertiary)]">
          {feature.toolingAndBackend && (
            <div className="flex items-baseline gap-2 max-w-full truncate">
              <span className="text-[10px] uppercase tracking-wider text-[var(--color-ink-tertiary)] shrink-0">
                Source:
              </span>
              <span className="text-[var(--color-ink)] truncate select-all">
                {feature.toolingAndBackend}
              </span>
            </div>
          )}

          {feature.decisionRefs?.length > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-[10px] uppercase tracking-wider text-[var(--color-ink-tertiary)]">
                Decisions:
              </span>
              <span className="text-[var(--color-ink)]">
                {feature.decisionRefs.map((d) => `§ ${d}`).join(', ')}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Sub-features: Minimal, clean, and expandable */}
      {feature.subFeatures?.length > 0 && (
        <div className="mt-6 pt-4 border-t border-[var(--color-line)]">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center justify-between w-full text-xs font-mono text-[var(--color-ink-secondary)] hover:text-[var(--color-accent)] transition-colors py-1"
          >
            <span>
              Sub-Features ({feature.subFeatures.length})
            </span>
            {isExpanded ? (
              <ChevronUp className="w-3.5 h-3.5" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5" />
            )}
          </button>

          {isExpanded && (
            <div className="mt-2 space-y-3 pl-4 border-l border-[var(--color-line)]">
              {feature.subFeatures.map((sub) => (
                <SubFeatureItem key={sub.id} feature={sub} />
              ))}
            </div>
          )}
        </div>
      )}
    </article>
  );
}
