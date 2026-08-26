# Halbert Brand Identity & Vector Assets

This directory hosts the official vector emblems, optical size tiers, favicons, and banners for Halbert.

---

## 1. Optical Sizing Tiers

The Halbert mark is engineered into four optical densities to preserve legibility and aesthetic balance across all display sizes:

| Tier | Shapes (% of Original) | Elements | Pitch | Stroke Width | Target Size | Primary Use Case |
|---|---|---|---|---|---|---|
| **Display** | 100% (10 paths) | 1 Spine + 9 U-curves | 48.0px | 26.67px | `>= 96px` | Marketing hero, splash screen, print, banners |
| **Medium** | 60% (6 paths) | 1 Spine + 5 U-curves | 86.4px | 48.00px | `32px - 96px` | Web & App navigation headers, cards, buttons |
| **Compact** | 40% (4 paths) | 1 Spine + 3 U-curves | 144.0px | 80.00px | `24px - 32px` | Sidebar navigation, secondary controls |
| **Small** | 30% (3 paths) | 1 Spine + 2 U-curves | 216.0px | 116.00px | `16px - 24px` | Browser favicons, OS status bar, micro-icons |

---

## 2. Palette & Semantic Colorways

- **Signature Accent**: Olivetti Vermilion (`#D34E24`)
- **Canvas**: Warm Archival Paper (`#F7F5F0`)
- **Carbon Ink**: Deep Charcoal (`#1A1918`)
- **Secondary Ink**: Graphite (`#5E5B56`)

Each tier is available in:
- `halbert-mark-{tier}.svg` — Adaptive `currentColor` with transparent background
- `halbert-mark-{tier}-vermilion.svg` — Vermilion on transparent
- `halbert-mark-{tier}-vermilion-on-canvas.svg` — Vermilion on warm paper canvas
- `halbert-mark-{tier}-charcoal.svg` — Charcoal ink on transparent
- `halbert-mark-{tier}-charcoal-on-canvas.svg` — Charcoal ink on canvas
- `halbert-mark-{tier}-badge.svg` — Inverted canvas mark on rounded Vermilion tile (`rx=224`)

---

## 3. Favicon Assets

- `favicon.svg` — Vector favicon optimized using the Small 3-track tier with rounded canvas tile
- `favicon-16x16.png` — 16x16 raster favicon
- `favicon-32x32.png` — 32x32 standard retina favicon
- `apple-touch-icon.png` — 180x180 iOS / mobile touch icon
- `favicon.ico` — Multi-resolution ICO container (16x16 + 32x32)

---

## 4. GitHub README Banners

- `halbert-readme-banner.svg` — Horizontal brand banner for light-mode GitHub display (1280x320)
- `halbert-readme-banner-dark.svg` — Horizontal brand banner for dark-mode GitHub display (1280x320)

---

## 5. React Integration

Use the official React component from `@halbert/design-system`:

```tsx
import { HalbertMark } from '@halbert/design-system'

// Auto optical sizing (default):
<HalbertMark size={16} />  // Automatically selects Small (3 tracks)
<HalbertMark size={48} />  // Automatically selects Medium (6 tracks)
<HalbertMark size={140} /> // Automatically selects Display (10 tracks)

// Explicit overrides:
<HalbertMark size={32} density="medium" tone="accent" />
<HalbertMark size={24} density="small" tone="badge" />
```
