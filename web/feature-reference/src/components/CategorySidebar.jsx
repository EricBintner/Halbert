import React from 'react';

export function CategorySidebar({
  categories,
  activeCategory,
  onSelectCategory,
  statusFilter,
  onStatusFilterChange,
  statusCounts,
  expandAll,
  onToggleExpandAll,
}) {
  const STATUSES = [
    { id: 'all', label: 'All' },
    { id: 'shipped', label: 'Shipped' },
    { id: 'hidden', label: 'Backend-only' },
    { id: 'unbuilt', label: 'Unbuilt' },
    { id: 'deferred', label: 'Deferred' },
  ];

  return (
    <aside className="w-64 shrink-0 hidden lg:block sticky top-20 self-start max-h-[calc(100vh-6rem)] overflow-y-auto pr-6 scrollbar-thin select-none">
      {/* Navigation Title & Expand toggle */}
      <div className="pb-3 mb-4 border-b border-[var(--color-line)] flex items-center justify-between">
        <span className="font-mono text-xs uppercase tracking-wider text-[var(--color-ink-tertiary)] font-semibold">
          Categories
        </span>
        <button
          onClick={onToggleExpandAll}
          className="font-mono text-xs text-[var(--color-ink-secondary)] hover:text-[var(--color-accent)] transition-colors"
        >
          {expandAll ? 'Collapse' : 'Expand'}
        </button>
      </div>

      {/* Category List */}
      <nav className="flex flex-col space-y-1 mb-8" aria-label="Feature categories">
        <a
          href="#top"
          onClick={(e) => {
            e.preventDefault();
            onSelectCategory('all');
            window.scrollTo({ top: 0, behavior: 'smooth' });
          }}
          className={`px-2.5 py-1.5 rounded text-xs font-mono transition-colors block ${
            activeCategory === 'all'
              ? 'text-[var(--color-accent)] font-semibold bg-[var(--color-surface-subtle)]'
              : 'text-[var(--color-ink-secondary)] hover:text-[var(--color-ink)]'
          }`}
        >
          00. Overview
        </a>

        {categories.map((cat, idx) => {
          const catId = cat.id || cat.name.toLowerCase().replace(/[^a-z0-9]+/g, '-');
          const isActive = activeCategory === (cat.id || cat.name);
          const indexNumber = String(idx + 1).padStart(2, '0');

          return (
            <a
              key={catId}
              href={`#category-${catId}`}
              onClick={() => onSelectCategory(cat.id || cat.name)}
              className={`px-2.5 py-1.5 rounded text-xs font-mono transition-colors block ${
                isActive
                  ? 'text-[var(--color-accent)] font-semibold bg-[var(--color-surface-subtle)]'
                  : 'text-[var(--color-ink-secondary)] hover:text-[var(--color-ink)]'
              }`}
            >
              {indexNumber}. {cat.name}
            </a>
          );
        })}
      </nav>

      {/* Status Filter: Minimal flat list, zero pills */}
      <div className="pt-4 border-t border-[var(--color-line)]">
        <div className="font-mono text-xs uppercase tracking-wider text-[var(--color-ink-tertiary)] font-semibold mb-2">
          Filter Status
        </div>
        <div className="flex flex-col space-y-1">
          {STATUSES.map((st) => {
            const isSelected = statusFilter === st.id;
            const count = statusCounts[st.id] ?? 0;
            return (
              <button
                key={st.id}
                onClick={() => onStatusFilterChange(st.id)}
                className={`flex items-center justify-between px-2.5 py-1 rounded text-xs font-mono transition-colors text-left ${
                  isSelected
                    ? 'text-[var(--color-accent)] font-semibold bg-[var(--color-surface-subtle)]'
                    : 'text-[var(--color-ink-secondary)] hover:text-[var(--color-ink)]'
                }`}
              >
                <span>{st.label}</span>
                <span className="text-[10px] text-[var(--color-ink-tertiary)]">{count}</span>
              </button>
            );
          })}
        </div>
      </div>
    </aside>
  );
}
