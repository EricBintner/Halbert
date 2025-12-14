# Domain Component Design System

This document defines the standard sizing, colors, and styling for all domain components.

## Icon Button Standards

### Sizes
| Size | Button | Icon | @ Font |
|------|--------|------|--------|
| `sm` | `h-7 w-7` | `h-4 w-4` | `text-sm font-bold` |
| `default` | `h-8 w-8` | `h-4 w-4` | `text-base font-bold` |

**Note**: Icons are always `h-4 w-4` for consistency. The @ symbol is slightly larger than icons because it visually appears smaller at the same font size.

### Colors (Inactive State)
All action buttons use `text-muted-foreground/60` for the inactive state.

### Hover Colors
| Action | Hover Color | Background |
|--------|-------------|------------|
| @ Mention | `text-blue-500` | `bg-blue-500/10` |
| Chat | `text-primary` | `bg-primary/10` |
| Research | `text-purple-500` | `bg-purple-500/10` |
| WhyBrain (defined) | `text-pink-500` | - |
| WhyBrain (undefined) | `text-muted-foreground` | `bg-accent` |

## Components Using This System

- `SystemItemActions` - @ mention, chat, research buttons
- `WhyBrain` - Brain icon for "why" explanations
- Services.tsx play/stop/restart buttons

## Usage Example

```tsx
// All pages should use size="sm" for row actions
<WhyBrain
  itemId={`service:${name}`}
  itemName={name}
  itemType="service"
  size="sm"
/>
<SystemItemActions
  item={{ name, type: 'service', id }}
  size="sm"
/>
```

## Status Badge Colors

Using `StatusBadge` component with `variant="outline"`:

| Severity | Light Mode | Dark Mode |
|----------|------------|-----------|
| success | `bg-green-500/15 text-green-700` | `bg-green-900/40 text-green-300` |
| warning | `bg-yellow-500/15 text-yellow-700` | `bg-yellow-900/40 text-yellow-300` |
| critical | `bg-red-500/15 text-red-700` | `bg-red-900/40 text-red-300` |
| info | `bg-sky-500/15 text-sky-700` | `bg-sky-900/40 text-sky-300` |
| unknown/stopped | `bg-muted text-muted-foreground` | (same) |
