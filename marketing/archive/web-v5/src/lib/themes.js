/**
 * Authentic Period Print Themes (Site V5)
 */

export const THEMES = [
  {
    id: 'cobalt-1968',
    name: '1968 Cobalt Blue Print Stock (Default)',
    description: 'Medium royal cobalt ink with pure paper white retro serif headlines.',
    preview: {
      canvas: '#1E40AF',
      ink: '#FFFFFF',
      accent: '#FFFFFF',
    },
    tokens: {
      '--color-canvas': '#1E40AF',
      '--color-surface': '#1D4ED8',
      '--color-surface-subtle': '#1E3A8A',
      '--color-surface-muted': '#3B82F6',
      '--color-ink': '#FFFFFF',
      '--color-ink-secondary': '#F8FAFC',
      '--color-ink-tertiary': '#BFDBFE',
      '--color-ink-ghost': '#60A5FA',
      '--color-accent': '#FFFFFF',
      '--color-accent-ochre': '#FCD34D',
    },
  },
  {
    id: 'archival-newsprint',
    name: '1968 Archival Newsprint',
    description: 'Uncoated warm newsprint with deep carbon black ink.',
    preview: {
      canvas: '#F4EFE6',
      ink: '#111827',
      accent: '#B91C1C',
    },
    tokens: {
      '--color-canvas': '#F4EFE6',
      '--color-surface': '#EBE3D5',
      '--color-surface-subtle': '#DFD6C3',
      '--color-surface-muted': '#9CA3AF',
      '--color-ink': '#111827',
      '--color-ink-secondary': '#1F2937',
      '--color-ink-tertiary': '#4B5563',
      '--color-ink-ghost': '#9CA3AF',
      '--color-accent': '#111827',
      '--color-accent-ochre': '#B91C1C',
    },
  },
  {
    id: 'olivetti-vermilion',
    name: '1968 Olivetti Letterpress Vermilion',
    description: 'Letterpress vermilion with warm bone-white type.',
    preview: {
      canvas: '#C2410C',
      ink: '#FFFBEB',
      accent: '#FFFBEB',
    },
    tokens: {
      '--color-canvas': '#C2410C',
      '--color-surface': '#9A3412',
      '--color-surface-subtle': '#7C2D12',
      '--color-surface-muted': '#EA580C',
      '--color-ink': '#FFFBEB',
      '--color-ink-secondary': '#FEF3C7',
      '--color-ink-tertiary': '#FDE68A',
      '--color-ink-ghost': '#FDBA74',
      '--color-accent': '#FFFBEB',
      '--color-accent-ochre': '#FCD34D',
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
    localStorage.setItem('halbert_dev_theme_v5', theme.id);
  } catch (e) {}

  return theme;
}

export function getSavedTheme(defaultThemeId = 'cobalt-1968') {
  try {
    const saved = localStorage.getItem('halbert_dev_theme_v5');
    if (saved && THEMES.some((t) => t.id === saved)) {
      return saved;
    }
  } catch (e) {}
  return defaultThemeId;
}
