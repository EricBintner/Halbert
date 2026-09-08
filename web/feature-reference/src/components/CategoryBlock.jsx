import React from 'react';
import { FeatureDossier } from './FeatureDossier';

export function CategoryBlock({ category, index, features, forceOpen }) {
  const catId = category.id || category.name.toLowerCase().replace(/[^a-z0-9]+/g, '-');
  const indexNumber = String(index + 1).padStart(2, '0');

  if (features.length === 0) return null;

  return (
    <section id={`category-${catId}`} className="scroll-mt-24 mb-20">
      {/* Quiet, Single-Tone Category Header */}
      <header className="pb-6 mb-8 border-b border-[var(--color-line)]">
        <div className="font-mono text-xs text-[var(--color-ink-tertiary)] uppercase tracking-wider mb-1">
          {indexNumber}
        </div>
        <h2 className="font-display font-semibold text-3xl sm:text-4xl text-[var(--color-ink)] tracking-tight">
          {category.name}
        </h2>
        {category.description && (
          <p className="mt-2 text-base text-[var(--color-ink-secondary)] font-sans max-w-2xl leading-relaxed">
            {category.description}
          </p>
        )}
      </header>

      {/* Spaced out Feature Plates */}
      <div className="flex flex-col space-y-8">
        {features.map((feature) => (
          <FeatureDossier
            key={feature.id}
            feature={feature}
            forceOpen={forceOpen}
          />
        ))}
      </div>
    </section>
  );
}
