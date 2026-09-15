import React, { useState, useEffect, useMemo } from 'react';
import catalog from './catalog.json';
import citationsData from '@halbert/shared/researchCitations.json';
import { FolioHeader } from './components/FolioHeader';
import { VectorParallaxBackground } from './components/VectorParallaxBackground';
import { CategorySidebar } from './components/CategorySidebar';
import { CategoryBlock } from './components/CategoryBlock';
import { CommandPalette } from './components/CommandPalette';
import { CitationBlock } from './components/CitationBlock';

// Research & Foundations: a pseudo-category alongside the feature categories
// (plan §5.3). Counts derive from the JSON, never typed.
const RESEARCH_CATEGORY_ID = 'research-foundations';

export function App() {
  const [activeCategory, setActiveCategory] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [scopeFilter, setScopeFilter] = useState('all');
  const [expandAll, setExpandAll] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);

  // Theme management: defaults to light (Daylight), supports dark (After Hours)
  const [theme, setTheme] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('hb_theme') || 'light';
    }
    return 'light';
  });

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
      root.setAttribute('data-theme', 'dark');
    } else {
      root.classList.remove('dark');
      root.removeAttribute('data-theme');
    }
    localStorage.setItem('hb_theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  // Keyboard shortcut: '/' opens CommandPalette search
  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.key === '/' && document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const categories = catalog.categories || [];
  const rawFeatures = catalog.features || [];

  // Research citations, sorted by year then title (plan §6 Step 3).
  const citations = useMemo(() => {
    const all = citationsData?.citations || [];
    return [...all].sort((a, b) => a.year - b.year || a.title.localeCompare(b.title));
  }, []);

  // Citation lookup by id, for FeatureDossier's foundations block.
  const citationsByCitationId = useMemo(() => {
    const map = {};
    citations.forEach((c) => {
      map[c.id] = c;
    });
    return map;
  }, [citations]);

  // Derived reverse join (plan §3.1): features carry citationIds; the
  // citation → features direction is computed here at load, never stored.
  // Derived among ALL features — this is the reference dictionary, hidden and
  // deferred features stay visible per the site's existing behaviour.
  const featuresByCitationId = useMemo(() => {
    const map = {};
    rawFeatures.forEach((f) => {
      (f.citationIds || []).forEach((id) => {
        if (!map[id]) map[id] = [];
        map[id].push(f.id);
      });
    });
    return map;
  }, [rawFeatures]);

  // Status counts
  const statusCounts = useMemo(() => {
    const counts = { all: 0, shipped: 0, hidden: 0, unbuilt: 0, deferred: 0 };
    rawFeatures.forEach((f) => {
      counts.all += 1;
      counts[f.status] = (counts[f.status] || 0) + 1;
    });
    return counts;
  }, [rawFeatures]);

  // Scope counts
  const scopeCounts = useMemo(() => {
    const counts = { all: rawFeatures.length, workstation: 0, home: 0 };
    rawFeatures.forEach((f) => {
      const scope = f.scope || [];
      if (scope.includes('workstation')) counts.workstation += 1;
      if (scope.includes('home')) counts.home += 1;
    });
    return counts;
  }, [rawFeatures]);

  // Category counts
  const categoryCounts = useMemo(() => {
    const counts = {};
    rawFeatures.forEach((f) => {
      counts[f.category] = (counts[f.category] || 0) + 1;
    });
    return counts;
  }, [rawFeatures]);

  // Filter features by status, scope, and activeCategory
  const filteredFeatures = useMemo(() => {
    return rawFeatures.filter((f) => {
      if (statusFilter !== 'all' && f.status !== statusFilter) return false;
      if (scopeFilter !== 'all') {
        const scope = f.scope || [];
        if (!scope.includes(scopeFilter)) return false;
      }
      if (
        activeCategory !== 'all' &&
        activeCategory !== RESEARCH_CATEGORY_ID &&
        f.category !== activeCategory &&
        f.category?.toLowerCase().replace(/[^a-z0-9]+/g, '-') !== activeCategory &&
        !categories.some(
          (cat) => f.category === cat.name && (cat.id || cat.name) === activeCategory
        )
      ) {
        return false;
      }
      return true;
    });
  }, [rawFeatures, categories, statusFilter, scopeFilter, activeCategory]);

  // Jump to a specific feature from the CommandPalette or a "Cited by" chip.
  // The feature may live in a category that is not currently rendered (the
  // Research view replaces the feature sections), so resolve the feature's
  // category first and re-render before scrolling.
  const handleSelectFeature = (featureId) => {
    const scrollToFeature = () => {
      const el = document.getElementById(featureId);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    };

    const feature = rawFeatures.find((f) => f.id === featureId);
    const owningCategory = categories.find((cat) => cat.name === feature?.category);

    if (
      (activeCategory === RESEARCH_CATEGORY_ID ||
        (owningCategory && activeCategory !== 'all' &&
         owningCategory.name !== activeCategory &&
         (owningCategory.id || owningCategory.name) !== activeCategory)) ||
      (statusFilter !== 'all' && feature?.status !== statusFilter) ||
      (scopeFilter !== 'all' && !feature?.scope?.includes(scopeFilter))
    ) {
      setStatusFilter('all');
      setScopeFilter('all');
      if (owningCategory) {
        setActiveCategory(owningCategory.id || owningCategory.name);
      } else if (activeCategory === RESEARCH_CATEGORY_ID) {
        setActiveCategory('all');
      }
      // Wait for the re-render to mount the target feature's dossier.
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          scrollToFeature();
        });
      });
      return;
    }

    scrollToFeature();
  };

  return (
    <div className="min-h-screen bg-[var(--color-canvas)] text-[var(--color-ink)] transition-colors relative selection:bg-[var(--color-accent)] selection:text-[var(--color-ink-on-accent)]">
      {/* Subtle Parametric Vector Parallax Background */}
      <VectorParallaxBackground />

      {/* Folio Brand Header identical to marketing site */}
      <FolioHeader
        theme={theme}
        onToggleTheme={toggleTheme}
        onOpenSearch={() => setSearchOpen(true)}
        featureCount={rawFeatures.length}
        categoryCount={categories.length}
      />

      {/* Main Container Stage */}
      <div className="relative z-10 max-w-[1440px] mx-auto px-6 sm:px-8 lg:px-12 pt-28 pb-32">
        {/* Editorial Hero Banner */}
        <section className="mb-16 pb-10 border-b border-[var(--color-line)] max-w-3xl" id="top">
          <div className="font-mono text-xs uppercase tracking-wider text-[var(--color-ink-tertiary)] mb-2 font-semibold">
            Design Problems Solved · Innovative Features
          </div>

          <h1 className="font-display font-semibold text-4xl sm:text-5xl lg:text-6xl text-[var(--color-ink)] tracking-tight leading-[1.1]">
            Feature Reference
          </h1>

          <p className="mt-4 text-base sm:text-lg text-[var(--color-ink-secondary)] font-sans leading-relaxed">
            Every capability in Halbert — what problem it solves, how it works under the hood, and the invariants that keep it safe.
          </p>
        </section>

        {/* Two-Column Stage: Left Sidebar + Right Editorial Dossiers */}
        <div className="flex items-start gap-12 lg:gap-16">
          {/* Side Menu Navigation */}
          <CategorySidebar
            categories={categories}
            activeCategory={activeCategory}
            onSelectCategory={setActiveCategory}
            categoryCounts={categoryCounts}
            statusFilter={statusFilter}
            onStatusFilterChange={setStatusFilter}
            statusCounts={statusCounts}
            scopeFilter={scopeFilter}
            onScopeFilterChange={setScopeFilter}
            scopeCounts={scopeCounts}
            expandAll={expandAll}
            onToggleExpandAll={() => setExpandAll(!expandAll)}
            researchCount={citations.length}
          />

          {/* Main Content Sections */}
          <main className="flex-1 min-w-0">
            {activeCategory === RESEARCH_CATEGORY_ID ? (
              <section id="category-research-foundations" className="scroll-mt-24 mb-20">
                <header className="pb-6 mb-8 border-b border-[var(--color-line)]">
                  <div className="font-mono text-xs text-[var(--color-ink-tertiary)] uppercase tracking-wider mb-1">
                    {String(categories.length + 1).padStart(2, '0')}
                  </div>
                  <h2 className="font-display font-semibold text-3xl sm:text-4xl text-[var(--color-ink)] tracking-tight">
                    Research &amp; Foundations
                  </h2>
                  <p className="mt-2 text-base text-[var(--color-ink-secondary)] font-sans max-w-2xl leading-relaxed">
                    The papers, RFCs, specifications, and engineering reports
                    that ground Halbert's architecture — the complete
                    bibliography, each entry with the features that cite it.
                  </p>
                </header>

                <div className="flex flex-col space-y-8">
                  {citations.map((citation) => {
                    const citingFeatureIds = featuresByCitationId[citation.id] || [];
                    const citingFeatures = citingFeatureIds
                      .map((id) => rawFeatures.find((f) => f.id === id))
                      .filter(Boolean);
                    return (
                      <div key={citation.id} id={`citation-${citation.id}`}>
                        <CitationBlock citation={citation} />
                        {citingFeatures.length > 0 && (
                          <div className="mt-2 flex flex-wrap items-center gap-2">
                            <span className="text-[10px] font-mono uppercase tracking-wider text-[var(--color-ink-tertiary)] shrink-0">
                              Cited by:
                            </span>
                            {citingFeatures.map((feature) => (
                              <button
                                key={feature.id}
                                onClick={() => handleSelectFeature(feature.id)}
                                className="font-mono text-[11px] text-[var(--color-ink)] border border-[var(--color-line)] bg-[var(--color-surface)] px-2 py-0.5 rounded-sm hover:text-[var(--color-accent)] hover:border-[var(--color-accent)] transition-colors"
                              >
                                {feature.name}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </section>
            ) : (
              <>
                {categories.map((cat, idx) => {
                  const feats = filteredFeatures.filter(
                    (f) => f.category === cat.name
                  );
                  return (
                    <CategoryBlock
                      key={cat.id || cat.name}
                      category={cat}
                      index={idx}
                      features={feats}
                      forceOpen={expandAll}
                      citationsByCitationId={citationsByCitationId}
                    />
                  );
                })}

                {filteredFeatures.length === 0 && (
                  <div className="py-24 text-center border border-dashed border-[var(--color-line)] rounded-xl bg-[var(--color-surface)]">
                    <p className="font-mono text-sm text-[var(--color-ink-secondary)] mb-3">
                      No specifications match the selected filters.
                    </p>
                    <button
                      onClick={() => {
                        setStatusFilter('all');
                        setScopeFilter('all');
                        setActiveCategory('all');
                      }}
                      className="font-mono text-xs font-bold text-[var(--color-accent)] hover:underline"
                    >
                      RESET FILTERS
                    </button>
                  </div>
                )}
              </>
            )}
          </main>
        </div>
      </div>

      {/* Global Command Palette Modal */}
      <CommandPalette
        isOpen={searchOpen}
        onClose={() => setSearchOpen(false)}
        features={rawFeatures}
        citations={citations}
        featuresByCitationId={featuresByCitationId}
        onSelectFeature={handleSelectFeature}
      />

      {/* Folio Footer */}
      <footer className="relative z-10 border-t border-[var(--color-line)] bg-[var(--color-surface)] py-12 text-xs font-mono text-[var(--color-ink-tertiary)]">
        <div className="max-w-[1440px] mx-auto px-6 sm:px-8 lg:px-12 flex flex-col sm:flex-row justify-between items-center gap-4">
          <div className="flex items-center space-x-3">
            <span className="font-bold text-[var(--color-ink)] tracking-wider">HALBERT</span>
            <span>·</span>
            <span>Marcello Nizzoli & Ettore Sottsass at Olivetti</span>
          </div>
          <div>
            Universal Design Tokens · GPL-3.0 License · Zero Tracking
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;
