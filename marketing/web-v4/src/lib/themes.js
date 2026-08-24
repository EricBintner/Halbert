/**
 * Minimalist Color Themes (Site V4)
 */

export const THEMES = [
  {
    id: 'studio-light',
    name: 'Studio Light (Default)',
    description: 'Crisp studio white canvas with deep slate carbon and electric cobalt accent.',
    preview: {
      canvas: '#FAFAFA',
      ink: '#0F172A',
      accent: '#2563EB',
    },
    tokens: {
      '--color-canvas': '#FAFAFA',
      '--color-surface': '#FFFFFF',
      '--color-surface-subtle': '#F1F5F9',
      '--color-surface-muted': '#E2E8F0',
      '--color-accent': '#0F172A',
      '--color-accent-hover': '#1E293B',
      '--color-accent-active': '#020617',
      '--color-brand-blue': '#2563EB',
      '--color-ink': '#0F172A',
      '--color-ink-secondary': '#475569',
      '--color-ink-tertiary': '#94A3B8',
      '--color-ink-ghost': '#CBD5E1',
      '--color-status-success': '#10B981',
      '--color-status-warning': '#F59E0B',
      '--color-status-error': '#EF4444',
      '--color-status-info': '#3B82F6',
    },
  },
  {
    id: 'warm-alabaster',
    name: 'Warm Alabaster & Amber',
    description: 'Soft unbleached paper tone with warm graphite and sunlit amber.',
    preview: {
      canvas: '#F7F6F2',
      ink: '#1C1917',
      accent: '#D97706',
    },
    tokens: {
      '--color-canvas': '#F7F6F2',
      '--color-surface': '#FFFFFF',
      '--color-surface-subtle': '#EFECE6',
      '--color-surface-muted': '#E2DDD4',
      '--color-accent': '#1C1917',
      '--color-accent-hover': '#292524',
      '--color-accent-active': '#0C0A09',
      '--color-brand-blue': '#D97706',
      '--color-ink': '#1C1917',
      '--color-ink-secondary': '#57534E',
      '--color-ink-tertiary': '#8C857E',
      '--color-ink-ghost': '#D6D3D1',
      '--color-status-success': '#15803D',
      '--color-status-warning': '#D97706',
      '--color-status-error': '#DC2626',
      '--color-status-info': '#2563EB',
    },
  },
  {
    id: 'nordic-ice',
    name: 'Nordic Ice & Teal',
    description: 'Cool glacial white with deep navy charcoal and marine teal.',
    preview: {
      canvas: '#F8FAFC',
      ink: '#0F172A',
      accent: '#0D9488',
    },
    tokens: {
      '--color-canvas': '#F8FAFC',
      '--color-surface': '#FFFFFF',
      '--color-surface-subtle': '#EDF2F7',
      '--color-surface-muted': '#E2E8F0',
      '--color-accent': '#0F172A',
      '--color-accent-hover': '#1E293B',
      '--color-accent-active': '#020617',
      '--color-brand-blue': '#0D9488',
      '--color-ink': '#0F172A',
      '--color-ink-secondary': '#334155',
      '--color-ink-tertiary': '#64748B',
      '--color-ink-ghost': '#CBD5E1',
      '--color-status-success': '#059669',
      '--color-status-warning': '#D97706',
      '--color-status-error': '#E11D48',
      '--color-status-info': '#0284C7',
    },
  },
];

export function applyTheme(themeId) {
  const theme = THEMES.find((t) => t.id === themeId) || THEMES[0];
  const root = document.documentElement;
  
  Object.entries(theme.tokens).forEach(([property, value]) => {
    root.style.setProperty(property, value);
  });

  root.style.backgroundColor = theme.tokens['--color-canvas'];
  document.body.style.backgroundColor = theme.tokens['--color-canvas'];
  root.style.color = theme.tokens['--color-ink'];
  document.body.style.color = theme.tokens['--color-ink'];

  try {
    localStorage.setItem('halbert_dev_theme_v4', theme.id);
  } catch (e) {}

  return theme;
}

export function getSavedTheme(defaultThemeId = 'studio-light') {
  try {
    const saved = localStorage.getItem('halbert_dev_theme_v4');
    if (saved && THEMES.some((t) => t.id === saved)) {
      return saved;
    }
  } catch (e) {}
  return defaultThemeId;
}
