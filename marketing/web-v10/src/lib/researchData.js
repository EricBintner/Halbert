/**
 * researchData — the dossier's pure data layer (no React).
 *
 * One copy of each dataset, aliased in from both marketing sites (plan
 * §6 Step 2): the citation dictionary lives in marketing/shared, the
 * feature catalog in marketing/feature-reference/src. Nothing here edits
 * either file; everything is derived at load, and every count the UI
 * shows is computed from these arrays — never typed in a string.
 *
 * Join rule (plan §3.1, one direction only): features carry
 * `citationIds`; citations never carry a reverse list. The reverse
 * mapping is DERIVED here at load (featuresForCitation), never stored,
 * so two join directions cannot drift.
 *
 * Visibility rule: the marketing dossier surfaces only `shipped`
 * features (status enum from the catalog). The reference site keeps the
 * full, unfiltered dictionary.
 */

import citationsJson from '@halbert/shared/researchCitations.json';
import catalog from '@halbert/catalog';

const RAW_CITATIONS = Array.isArray(citationsJson?.citations) ? citationsJson.citations : [];

/**
 * All citations, ordered as a stable bibliography: year ascending, then
 * title. Cards render in this order everywhere.
 */
export const CITATIONS = [...RAW_CITATIONS].sort(
  (a, b) => a.year - b.year || String(a.title).localeCompare(String(b.title)),
);

/** The dossier's feature set: the catalog minus hidden/deferred features. */
export const SHIPPED_FEATURES = (Array.isArray(catalog?.features) ? catalog.features : []).filter(
  (f) => f.status === 'shipped',
);

/** Feature category id -> authored category name, in catalog order. */
export const CATEGORIES = Object.fromEntries(
  (Array.isArray(catalog?.categories) ? catalog.categories : []).map((c) => [c.id, c.name]),
);

/** Citations whose stopId matches the given storyboard stop. */
export function citationsForStop(stopId) {
  return CITATIONS.filter((c) => c.stopId === stopId);
}

/** Shipped features whose stopIds include the given storyboard stop. */
export function featuresForStop(stopId) {
  return SHIPPED_FEATURES.filter((f) => Array.isArray(f.stopIds) && f.stopIds.includes(stopId));
}

/** Derived reverse join: shipped features that cite this entry. */
export function featuresForCitation(citationId) {
  return SHIPPED_FEATURES.filter(
    (f) => Array.isArray(f.citationIds) && f.citationIds.includes(citationId),
  );
}

/**
 * The monospace citation line: "<authors> · <venue> · <identifier-or-year>".
 * An empty identifier falls back to the year (e.g. an engineering report
 * with no arXiv/DOI ends "... · Chroma technical report · 2025").
 */
export function formatCitation(c) {
  const tail = c.identifier && c.identifier.trim() ? c.identifier : String(c.year);
  return [c.authors, c.venue, tail].filter(Boolean).join(' · ');
}