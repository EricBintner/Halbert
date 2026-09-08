import React, { useState, useEffect, useMemo } from 'react';
import catalog from './catalog.json';
import { FolioHeader } from './components/FolioHeader';
import { VectorParallaxBackground } from './components/VectorParallaxBackground';
import { CategorySidebar } from './components/CategorySidebar';
import { CategoryBlock } from './components/CategoryBlock';
import { CommandPalette } from './components/CommandPalette';

export function App() {
  const [activeCategory, setActiveCategory] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
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

  // Status counts
  const statusCounts = useMemo(() => {
    const counts = { all: 0, shipped: 0, hidden: 0, unbuilt: 0, deferred: 0 };
    rawFeatures.forEach((f) => {
      counts.all += 1;
      counts[f.status] = (counts[f.status] || 0) + 1;
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

  // Filter features by status and activeCategory
  const filteredFeatures = useMemo(() => {
    return rawFeatures.filter((f) => {
      if (statusFilter !== 'all' && f.status !== statusFilter) return false;
      if (
        activeCategory !== 'all' &&
        f.category !== activeCategory &&
        f.category?.toLowerCase().replace(/[^a-z0-9]+/g, '-') !== activeCategory
      ) {
        return false;
      }
      return true;
    });
  }, [rawFeatures, statusFilter, activeCategory]);

  // Jump to specific feature from CommandPalette
  const handleSelectFeature = (featureId) => {
    const el = document.getElementById(featureId);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
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
            Architecture & Capability Inventory
          </div>

          <h1 className="font-display font-semibold text-4xl sm:text-5xl lg:text-6xl text-[var(--color-ink)] tracking-tight leading-[1.1]">
            Feature Reference
          </h1>

          <p className="mt-4 text-base sm:text-lg text-[var(--color-ink-secondary)] font-sans leading-relaxed">
            An engineering inventory of every subsystem, cognitive loop, and security boundary in Halbert.
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
            expandAll={expandAll}
            onToggleExpandAll={() => setExpandAll(!expandAll)}
          />

          {/* Main Content Sections */}
          <main className="flex-1 min-w-0">
            {categories.map((cat, idx) => {
              const feats = filteredFeatures.filter((f) => f.category === cat.name);
              return (
                <CategoryBlock
                  key={cat.id || cat.name}
                  category={cat}
                  index={idx}
                  features={feats}
                  forceOpen={expandAll}
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
                    setActiveCategory('all');
                  }}
                  className="font-mono text-xs font-bold text-[var(--color-accent)] hover:underline"
                >
                  RESET FILTERS
                </button>
              </div>
            )}
          </main>
        </div>
      </div>

      {/* Global Command Palette Modal */}
      <CommandPalette
        isOpen={searchOpen}
        onClose={() => setSearchOpen(false)}
        features={rawFeatures}
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
