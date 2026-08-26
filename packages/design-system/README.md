# @halbert/design-system

The Olivetti Vermilion & Bone component library, shared by the Halbert desktop
shell and the marketing site. Track 3 of the
[brand aesthetic roadmap](../../documentation/design/BRAND-AESTHETIC-STYLEGUIDE-AND-STORYBOOK-PLAN.md).

## Using it

```tsx
import { AppWindow, MetricCard, StatusBadge, Button } from '@halbert/design-system'
import '@halbert/design-system/styles.css'   // pulls in /shared-tokens/tokens.css

<AppWindow title="System Vitals" meta="updates every 5s" live>
  <MetricCard label="CPU temp" value="45°C" sub="Nominal · fans idle" tone="nominal" bar={38} />
</AppWindow>
```

## What's here

| Component | Role |
|---|---|
| `Button` | Primary / outline / ghost / danger, with `loading` and `asChild` |
| `StatusBadge` | Telemetry pill in the five semantic tones |
| `Input` | Tactile field with label, hint, and error wiring |
| `Select` | Styled native `<select>` |
| `ParametricSlider` | Headroom preview slider — ARC sizing, swappiness |
| `AppWindow` | The instrument plate: header strip, body, footer tray |
| `MetricCard` | Live sensor card with an optional gauge |

## Three decisions worth knowing

**Plain CSS, not Tailwind.** This library is consumed by one app on Tailwind v3
and another on v4. Utility classes in library source would need scanning by both
and would drift across the majors. Token variables are the portable layer, so
components use them directly and `styles.css` contains no literal colours.

**Native controls where the platform is already correct.** `Select` wraps a real
`<select>` and `ParametricSlider` wraps a real `<input type="range">`. Keyboard
handling, type-ahead, touch dragging, and screen-reader semantics all arrive
working; a hand-rolled listbox is a large accessibility surface to own in
exchange for styling freedom that CSS already provides.

**No runtime dependencies.** `asChild` is served by a ~20-line local `Slot`
rather than `@radix-ui/react-slot`, because every dependency here is a version
negotiation across React 18 (dashboard) and React 19 (marketing).

## Accessibility invariants the tests lock in

- `StatusBadge` requires a text child — colour alone fails WCAG 1.4.1.
- `Input` and `Select` require a `label`; a placeholder is not a label.
- `Button` blocks activation while `loading`, including via `asChild`, where
  there is no `disabled` attribute to lean on.
- `MetricCard` clamps out-of-range gauge values and renders `[Sensor offline]`
  rather than a plausible-looking zero.
- `ParametricSlider` carries `aria-valuetext` and is **not** a live region —
  it changes on every arrow keypress.

## Commands

```bash
npm install
npm run typecheck
npm test
```

Colour values come from `/shared-tokens/tokens.css` and are verified by
`python3 scripts/check_contrast.py` at the repo root. Never add a literal colour
to this package.
