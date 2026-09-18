/**
 * Mid-Century Modern & 1960s Futurist Color Theme Definitions
 * 
 * Curated color systems inspired by iconic industrial & graphic design eras:
 * 1. Bauhaus Signal Amber (Signal Amber & Drafting Bone)
 * 2. Olivetti 1968 (Vermilion on Warm Archival Paper)
 * 3. Braun Studio ET66 (Matte Platinum Stone & Signal Ochre)
 * 4. NASA 1975 (Apollo Worm Red & Laboratory Eggshell)
 * 5. Chartreuse & Teal (High-Contrast Italian Modernist)
 * 6. Swiss Cobalt & Ochre (1965 Total Design / Klein Blue)
 */

export const THEMES = [
  {
    id: 'bauhaus-amber',
    name: 'Bauhaus Amber',
    era: '1965 Technical Drafting',
    description: 'Matte architectural bone paper with Bauhaus laboratory signal amber and blueprint carbon.',
    preview: {
      canvas: '#F4F1EA',
      ink: '#121417',
      accent: '#E65C00',
    },
    tokens: {
      '--color-canvas': '#F4F1EA',
      '--color-surface': '#FFFFFF',
      '--color-surface-subtle': '#EBE6DC',
      '--color-surface-muted': '#DFD9CD',
      '--color-accent': '#E65C00',
      '--color-accent-hover': '#C74F00',
      '--color-accent-active': '#A84200',
      '--color-accent-tint': '#FFF3EB',
      '--color-ink': '#121417',
      '--color-ink-secondary': '#424851',
      '--color-ink-tertiary': '#767E8B',
      '--color-ink-ghost': '#B4BAC3',
      '--color-status-success': '#1E7B48',
      '--color-status-warning': '#D97706',
      '--color-status-error': '#DC2626',
      '--color-status-info': '#1B4965',
      '--color-blueprint': '#1B4965',
      '--color-blueprint-light': '#E8F1F5',
    },
  },
  {
    id: 'olivetti-1968',
    name: 'Olivetti 1968',
    era: 'Late 60s Futurist',
    description: 'Warm archival paper with signature Olivetti Valentine vermilion and deep charcoal carbon.',
    preview: {
      canvas: '#F7F5F0',
      ink: '#1A1918',
      accent: '#D34E24',
    },
    tokens: {
      '--color-canvas': '#F7F5F0',
      '--color-surface': '#FFFFFF',
      '--color-surface-subtle': '#EFECE4',
      '--color-surface-muted': '#E5E0D5',
      '--color-accent': '#D34E24',
      '--color-accent-hover': '#B83E18',
      '--color-accent-active': '#9C3212',
      '--color-accent-tint': '#FDF2EE',
      '--color-ink': '#1A1918',
      '--color-ink-secondary': '#4A4742',
      '--color-ink-tertiary': '#7A756D',
      '--color-ink-ghost': '#B8B2A6',
      '--color-status-success': '#2D7A56',
      '--color-status-warning': '#C4781C',
      '--color-status-error': '#C83E2D',
      '--color-status-info': '#386C8A',
      '--color-blueprint': '#1B4965',
      '--color-blueprint-light': '#E8F1F5',
    },
  },
  {
    id: 'braun-studio',
    name: 'Braun Studio ET66',
    era: 'Dieter Rams Minimalist',
    description: 'Matte anodized platinum stone with Braun ET66 signal ochre yellow and matte graphite.',
    preview: {
      canvas: '#ECEBE4',
      ink: '#1C1C1E',
      accent: '#E5A100',
    },
    tokens: {
      '--color-canvas': '#ECEBE4',
      '--color-surface': '#F9F9F6',
      '--color-surface-subtle': '#DFDED6',
      '--color-surface-muted': '#D2D0C6',
      '--color-accent': '#E5A100',
      '--color-accent-hover': '#C48800',
      '--color-accent-active': '#A37100',
      '--color-accent-tint': '#FEF9E6',
      '--color-ink': '#1C1C1E',
      '--color-ink-secondary': '#48484A',
      '--color-ink-tertiary': '#8E8E93',
      '--color-ink-ghost': '#C7C7CC',
      '--color-status-success': '#2D8A4E',
      '--color-status-warning': '#E07A00',
      '--color-status-error': '#D32F2F',
      '--color-status-info': '#2A6F97',
      '--color-blueprint': '#2A6F97',
      '--color-blueprint-light': '#E5EFF5',
    },
  },
  {
    id: 'nasa-1975',
    name: 'NASA 1975 Standards',
    era: 'Danne & Blackburn Manual',
    description: 'Apollo technical eggshell with iconic NASA Worm red and deep space obsidian ink.',
    preview: {
      canvas: '#F5F6F8',
      ink: '#0B0F19',
      accent: '#E03C31',
    },
    tokens: {
      '--color-canvas': '#F5F6F8',
      '--color-surface': '#FFFFFF',
      '--color-surface-subtle': '#E6E9EE',
      '--color-surface-muted': '#D5DAE2',
      '--color-accent': '#E03C31',
      '--color-accent-hover': '#C22B21',
      '--color-accent-active': '#9E1C13',
      '--color-accent-tint': '#FEECEB',
      '--color-ink': '#0B0F19',
      '--color-ink-secondary': '#384252',
      '--color-ink-tertiary': '#6B7A90',
      '--color-ink-ghost': '#9AA8BC',
      '--color-status-success': '#00875A',
      '--color-status-warning': '#FFAB00',
      '--color-status-error': '#DE350B',
      '--color-status-info': '#0052CC',
      '--color-blueprint': '#004F71',
      '--color-blueprint-light': '#E6F0F5',
    },
  },
  {
    id: 'chartreuse-teal',
    name: 'Chartreuse & Marine Teal',
    era: 'Italian Modernist / Vignelli',
    description: 'Soft chartreuse drafting wash with deep marine teal and dark pine forest ink.',
    preview: {
      canvas: '#F1F5E8',
      ink: '#132219',
      accent: '#0F766E',
    },
    tokens: {
      '--color-canvas': '#F1F5E8',
      '--color-surface': '#FCFDF8',
      '--color-surface-subtle': '#E3EBD2',
      '--color-surface-muted': '#D2DDBB',
      '--color-accent': '#0F766E',
      '--color-accent-hover': '#0D635C',
      '--color-accent-active': '#0B4F4A',
      '--color-accent-tint': '#E6F4F2',
      '--color-ink': '#132219',
      '--color-ink-secondary': '#324B3C',
      '--color-ink-tertiary': '#668070',
      '--color-ink-ghost': '#A3B5AA',
      '--color-status-success': '#16A34A',
      '--color-status-warning': '#D97706',
      '--color-status-error': '#DC2626',
      '--color-status-info': '#0284C7',
      '--color-blueprint': '#155E75',
      '--color-blueprint-light': '#E0F2FE',
    },
  },
  {
    id: 'swiss-cobalt',
    name: 'Swiss Cobalt & Ochre',
    era: '1965 Total Design',
    description: 'Warm limestone canvas with International Klein Cobalt Blue and midnight slate.',
    preview: {
      canvas: '#F6F4EE',
      ink: '#111827',
      accent: '#1A56DB',
    },
    tokens: {
      '--color-canvas': '#F6F4EE',
      '--color-surface': '#FFFFFF',
      '--color-surface-subtle': '#EAE6DC',
      '--color-surface-muted': '#DDD7CA',
      '--color-accent': '#1A56DB',
      '--color-accent-hover': '#1642AF',
      '--color-accent-active': '#12338A',
      '--color-accent-tint': '#EBF1FF',
      '--color-ink': '#111827',
      '--color-ink-secondary': '#374151',
      '--color-ink-tertiary': '#6B7280',
      '--color-ink-ghost': '#9CA3AF',
      '--color-status-success': '#059669',
      '--color-status-warning': '#D97706',
      '--color-status-error': '#DC2626',
      '--color-status-info': '#2563EB',
      '--color-blueprint': '#1E3A8A',
      '--color-blueprint-light': '#EFF6FF',
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
    localStorage.setItem('halbert_dev_theme_v2', theme.id);
  } catch (e) {}

  return theme;
}

export function getSavedTheme(defaultThemeId = 'bauhaus-amber') {
  try {
    const saved = localStorage.getItem('halbert_dev_theme_v2');
    if (saved && THEMES.some((t) => t.id === saved)) {
      return saved;
    }
  } catch (e) {}
  return defaultThemeId;
}
