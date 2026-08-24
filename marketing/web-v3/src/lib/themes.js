/**
 * Color Themes for Retro Serif Edition (Site V3)
 * Featuring rich medium blue, Aegean ultramarine, midnight navy, and mid-century palettes.
 */

export const THEMES = [
  {
    id: 'aegean-blue',
    name: 'Aegean Medium Blue (Default)',
    era: '1980s Retro Serif Editorial',
    description: 'Rich Mediterranean medium blue with crisp white retro serif headlines and champagne gold accents.',
    preview: {
      canvas: '#1B447A',
      ink: '#FFFFFF',
      accent: '#FCD34D',
    },
    tokens: {
      '--color-canvas': '#1B447A',
      '--color-surface': '#23528F',
      '--color-surface-subtle': '#153663',
      '--color-surface-muted': '#2D60A1',
      '--color-accent': '#FCD34D',
      '--color-accent-hover': '#F59E0B',
      '--color-accent-active': '#D97706',
      '--color-accent-tint': 'rgba(252, 211, 77, 0.15)',
      '--color-ink': '#FFFFFF',
      '--color-ink-secondary': '#E0E7FF',
      '--color-ink-tertiary': '#93C5FD',
      '--color-ink-ghost': '#60A5FA',
      '--color-status-success': '#34D399',
      '--color-status-warning': '#FBBF24',
      '--color-status-error': '#F87171',
      '--color-status-info': '#60A5FA',
    },
  },
  {
    id: 'apple-1984-cobalt',
    name: 'Apple 1984 French Cobalt',
    era: 'Macintosh Launch Edition',
    description: 'Deep French cobalt blue with bright paper white headlines and warm amber accents.',
    preview: {
      canvas: '#1E3A8A',
      ink: '#FFFFFF',
      accent: '#F59E0B',
    },
    tokens: {
      '--color-canvas': '#1E3A8A',
      '--color-surface': '#254BB5',
      '--color-surface-subtle': '#172C68',
      '--color-surface-muted': '#3258C7',
      '--color-accent': '#F59E0B',
      '--color-accent-hover': '#D97706',
      '--color-accent-active': '#B45309',
      '--color-accent-tint': 'rgba(245, 158, 11, 0.15)',
      '--color-ink': '#FFFFFF',
      '--color-ink-secondary': '#EEF2FF',
      '--color-ink-tertiary': '#A5B4FC',
      '--color-ink-ghost': '#818CF8',
      '--color-status-success': '#10B981',
      '--color-status-warning': '#F59E0B',
      '--color-status-error': '#EF4444',
      '--color-status-info': '#38BDF8',
    },
  },
  {
    id: 'vogue-peacock-teal',
    name: 'Vogue 1990 Peacock Teal',
    era: 'Late 80s Editorial Gloss',
    description: 'Lush dark peacock teal with milk-white headlines and coral vermilion highlights.',
    preview: {
      canvas: '#134E5E',
      ink: '#FFFFFF',
      accent: '#FF7A59',
    },
    tokens: {
      '--color-canvas': '#134E5E',
      '--color-surface': '#1C6B80',
      '--color-surface-subtle': '#0E3B47',
      '--color-surface-muted': '#257D96',
      '--color-accent': '#FF7A59',
      '--color-accent-hover': '#EA580C',
      '--color-accent-active': '#C2410C',
      '--color-accent-tint': 'rgba(255, 122, 89, 0.15)',
      '--color-ink': '#FFFFFF',
      '--color-ink-secondary': '#E6FFFA',
      '--color-ink-tertiary': '#99F6E4',
      '--color-ink-ghost': '#5EEAD4',
      '--color-status-success': '#2DD4BF',
      '--color-status-warning': '#FBBF24',
      '--color-status-error': '#F87171',
      '--color-status-info': '#38BDF8',
    },
  },
  {
    id: 'archival-bone',
    name: 'Archival Warm Paper (Light Alternative)',
    era: 'Literary Press',
    description: 'Warm unbleached paper with deep midnight blue headlines and vintage vermilion.',
    preview: {
      canvas: '#F7F4EE',
      ink: '#1A365D',
      accent: '#C53030',
    },
    tokens: {
      '--color-canvas': '#F7F4EE',
      '--color-surface': '#FFFFFF',
      '--color-surface-subtle': '#EDE8DC',
      '--color-surface-muted': '#DDD6C5',
      '--color-accent': '#C53030',
      '--color-accent-hover': '#9B2C2C',
      '--color-accent-active': '#742A2A',
      '--color-accent-tint': 'rgba(197, 48, 48, 0.12)',
      '--color-ink': '#1A365D',
      '--color-ink-secondary': '#2C5282',
      '--color-ink-tertiary': '#4A5568',
      '--color-ink-ghost': '#A0AEC0',
      '--color-status-success': '#276749',
      '--color-status-warning': '#D69E2E',
      '--color-status-error': '#E53E3E',
      '--color-status-info': '#3182CE',
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
    localStorage.setItem('halbert_dev_theme_v3', theme.id);
  } catch (e) {}

  return theme;
}

export function getSavedTheme(defaultThemeId = 'aegean-blue') {
  try {
    const saved = localStorage.getItem('halbert_dev_theme_v3');
    if (saved && THEMES.some((t) => t.id === saved)) {
      return saved;
    }
  } catch (e) {}
  return defaultThemeId;
}
