/**
 * Kinetic Palettes for Site V7
 */

export const THEMES = [
  {
    id: 'chartreuse-teal',
    name: 'Vignelli Pop Chartreuse & Teal (Default)',
    description: 'Vibrant chartreuse lime on deep Aegean cyan with CMYK bleed effects.',
    preview: {
      canvas: '#0F766E',
      ink: '#FFFFFF',
      accent: '#D4E157',
    },
    tokens: {
      '--color-canvas': '#0F766E',
      '--color-surface': '#115E59',
      '--color-surface-subtle': '#134E4A',
      '--color-vector-lime': '#D4E157',
      '--color-vector-light': '#E6EE9C',
      '--color-vector-glow': 'rgba(212, 225, 87, 0.35)',
      '--color-ink': '#FFFFFF',
      '--color-ink-secondary': '#CCFBF1',
      '--color-ink-tertiary': '#99F6E4',
      '--color-ink-on-stroke': '#042F2E',
    },
  },
  {
    id: 'olivetti-vermilion',
    name: '1968 Olivetti Vermilion & Bone',
    description: 'Letterpress vermilion vector strokes on warm archival linen.',
    preview: {
      canvas: '#F7F4EE',
      ink: '#1C1917',
      accent: '#D34E24',
    },
    tokens: {
      '--color-canvas': '#F7F4EE',
      '--color-surface': '#FFFFFF',
      '--color-surface-subtle': '#EDE8DC',
      '--color-vector-lime': '#D34E24',
      '--color-vector-light': '#F97316',
      '--color-vector-glow': 'rgba(211, 78, 36, 0.25)',
      '--color-ink': '#1C1917',
      '--color-ink-secondary': '#44403C',
      '--color-ink-tertiary': '#78716C',
      '--color-ink-on-stroke': '#FFF7ED',
    },
  },
  {
    id: 'swiss-cobalt',
    name: 'Swiss Cobalt & Signal Yellow',
    description: 'Klein cobalt blue canvas with signal yellow vector tracks.',
    preview: {
      canvas: '#1E40AF',
      ink: '#FFFFFF',
      accent: '#FDE047',
    },
    tokens: {
      '--color-canvas': '#1E40AF',
      '--color-surface': '#1D4ED8',
      '--color-surface-subtle': '#1E3A8A',
      '--color-vector-lime': '#FDE047',
      '--color-vector-light': '#FEF08A',
      '--color-vector-glow': 'rgba(253, 224, 71, 0.35)',
      '--color-ink': '#FFFFFF',
      '--color-ink-secondary': '#EFF6FF',
      '--color-ink-tertiary': '#BFDBFE',
      '--color-ink-on-stroke': '#1E3A8A',
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
    localStorage.setItem('halbert_dev_theme_v7', theme.id);
  } catch (e) {}

  return theme;
}

export function getSavedTheme(defaultThemeId = 'chartreuse-teal') {
  try {
    const saved = localStorage.getItem('halbert_dev_theme_v7');
    if (saved && THEMES.some((t) => t.id === saved)) {
      return saved;
    }
  } catch (e) {}
  return defaultThemeId;
}
