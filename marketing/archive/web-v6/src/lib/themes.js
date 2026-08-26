/**
 * Experimental Palettes (Site V6)
 */

export const THEMES = [
  {
    id: 'linen-violet',
    name: 'Gallery Linen & Blue-Violet (Default)',
    description: 'Warm off-white linen canvas with 80% light blue-violet geometric installation and CMYK bleeds.',
    preview: {
      canvas: '#FAF8F5',
      ink: '#121417',
      accent: '#818CF8',
    },
    tokens: {
      '--color-canvas': '#FAF8F5',
      '--color-surface': '#FFFFFF',
      '--color-surface-subtle': '#F0EDE6',
      '--color-surface-muted': '#E5E0D8',
      '--color-violet-light': '#C7D2FE',
      '--color-violet-primary': '#818CF8',
      '--color-violet-deep': '#6366F1',
      '--color-violet-dark': '#4F46E5',
      '--color-ink': '#121417',
      '--color-ink-secondary': '#4B5563',
      '--color-ink-tertiary': '#9CA3AF',
    },
  },
  {
    id: 'slate-periwinkle',
    name: 'Nordic Slate & Periwinkle',
    description: 'Subtle cool slate canvas with bright periwinkle and deep navy contrast.',
    preview: {
      canvas: '#F1F5F9',
      ink: '#0F172A',
      accent: '#6366F1',
    },
    tokens: {
      '--color-canvas': '#F1F5F9',
      '--color-surface': '#FFFFFF',
      '--color-surface-subtle': '#E2E8F0',
      '--color-surface-muted': '#CBD5E1',
      '--color-violet-light': '#E0E7FF',
      '--color-violet-primary': '#6366F1',
      '--color-violet-deep': '#4F46E5',
      '--color-violet-dark': '#3730A3',
      '--color-ink': '#0F172A',
      '--color-ink-secondary': '#334155',
      '--color-ink-tertiary': '#64748B',
    },
  },
  {
    id: 'charcoal-cyan',
    name: 'Dark Room & CMYK Cyan',
    description: 'Deep blueprint charcoal with luminous cyan and magenta bleeds.',
    preview: {
      canvas: '#0F172A',
      ink: '#F8FAFC',
      accent: '#00E5FF',
    },
    tokens: {
      '--color-canvas': '#0F172A',
      '--color-surface': '#1E293B',
      '--color-surface-subtle': '#0B1120',
      '--color-surface-muted': '#334155',
      '--color-violet-light': '#38BDF8',
      '--color-violet-primary': '#00E5FF',
      '--color-violet-deep': '#FF007A',
      '--color-violet-dark': '#818CF8',
      '--color-ink': '#F8FAFC',
      '--color-ink-secondary': '#CBD5E1',
      '--color-ink-tertiary': '#94A3B8',
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
    localStorage.setItem('halbert_dev_theme_v6', theme.id);
  } catch (e) {}

  return theme;
}

export function getSavedTheme(defaultThemeId = 'linen-violet') {
  try {
    const saved = localStorage.getItem('halbert_dev_theme_v6');
    if (saved && THEMES.some((t) => t.id === saved)) {
      return saved;
    }
  } catch (e) {}
  return defaultThemeId;
}
