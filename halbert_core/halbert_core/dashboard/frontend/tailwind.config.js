/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      /* Every family points at the token tier, so the stacks are defined once
       * in shared-tokens/tokens.css and Tailwind's preflight, the utilities and
       * the base rules cannot disagree. The old `grotesk` alias is gone —
       * `sans` IS Space Grotesk now. */
      fontFamily: {
        sans: ['var(--hb-font-sans)'],
        heading: ['var(--hb-font-display)'],
        display: ['var(--hb-font-display)'],
        mono: ['var(--hb-font-mono)'],
      },
      letterSpacing: {
        display: 'var(--tracking-display)',
        label: 'var(--tracking-label)',
      },
      boxShadow: {
        plate: "var(--shadow-plate)",
        subtle: "var(--shadow-subtle)",
        popover: "var(--shadow-popover)",
      },
      transitionTimingFunction: {
        shutter: "var(--ease-shutter)",
        switch: "var(--ease-switch)",
      },
      transitionDuration: {
        instant: "var(--duration-instant)",
        switch: "var(--duration-switch)",
        shutter: "var(--duration-shutter)",
      },
      colors: {
        /* ---- Halbert / Olivetti Vermilion & Bone -------------------------
         * Backed by /shared-tokens/tokens.css. These are plain CSS colour
         * values, not the `hsl(var(--x))` triplets shadcn uses, so they are
         * kept in their own namespaces (canvas/ink/accent/status) and do not
         * collide with the slots below. Use `bg-canvas`, `text-ink-secondary`,
         * `border-hairline`, `text-status-warning`, `ring-focus`.
         * ---------------------------------------------------------------- */
        canvas: {
          DEFAULT: "var(--color-canvas)",
          surface: "var(--color-surface)",
          subtle: "var(--color-surface-subtle)",
          muted: "var(--color-surface-muted)",
        },
        ink: {
          DEFAULT: "var(--color-ink)",
          secondary: "var(--color-ink-secondary)",
          tertiary: "var(--color-ink-tertiary)",
          ghost: "var(--color-ink-ghost)",
          "on-accent": "var(--color-ink-on-accent)",
        },
        vermilion: {
          DEFAULT: "var(--color-accent)",
          strong: "var(--color-accent-strong)",
          hover: "var(--color-accent-hover)",
          active: "var(--color-accent-active)",
          tint: "var(--color-accent-tint)",
        },
        status: {
          nominal: "var(--color-status-nominal)",
          "nominal-bg": "var(--color-status-nominal-bg)",
          "nominal-line": "var(--color-status-nominal-line)",
          warning: "var(--color-status-warning)",
          "warning-bg": "var(--color-status-warning-bg)",
          "warning-line": "var(--color-status-warning-line)",
          critical: "var(--color-status-critical)",
          "critical-bg": "var(--color-status-critical-bg)",
          "critical-line": "var(--color-status-critical-line)",
          telemetry: "var(--color-status-telemetry)",
          "telemetry-bg": "var(--color-status-telemetry-bg)",
          "telemetry-line": "var(--color-status-telemetry-line)",
        },
        hairline: {
          DEFAULT: "var(--color-line)",
          subtle: "var(--color-line-subtle)",
          strong: "var(--color-line-strong)",
        },
        focus: "var(--color-focus-ring)",

        border: "hsl(var(--border))",
        "border-subtle": "hsl(var(--border-subtle))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
          muted: "hsl(var(--primary-muted))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // SourcePrep semantic tokens
        surface: {
          DEFAULT: "hsl(var(--surface))",
          raised: "hsl(var(--surface-raised))",
        },
        text: {
          DEFAULT: "hsl(var(--text))",
          muted: "hsl(var(--text-muted))",
          subtle: "hsl(var(--text-subtle))",
          base: "hsl(var(--text-base))",
        },
        success: {
          DEFAULT: "hsl(var(--success))",
          muted: "hsl(var(--success-muted))",
        },
        error: {
          DEFAULT: "hsl(var(--error))",
          muted: "hsl(var(--error-muted))",
        },
        warning: {
          DEFAULT: "hsl(var(--warning))",
          muted: "hsl(var(--warning-muted))",
        },
        info: {
          DEFAULT: "hsl(var(--info))",
          muted: "hsl(var(--info-muted))",
        },
      },
      /* Point at the canonical radii instead of shadcn's derived --radius.
       * That variable was defined in the hand-written theme block this config
       * long predates; when the block became generated it stopped being
       * emitted, and `var(--radius)` with no fallback is invalid at
       * computed-value time — so every Card, Button, Input, Badge, Dialog and
       * Tab silently rendered with square corners while bare `rounded` and
       * `rounded-full` kept rounding. The token tier has no such gap. */
      borderRadius: {
        sm: "var(--hb-radius-sm)",
        md: "var(--hb-radius-md)",
        lg: "var(--hb-radius-lg)",
        full: "var(--hb-radius-full)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: 0 },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: 0 },
        },
        "pulse-subtle": {
          "0%, 100%": { opacity: 1 },
          "50%": { opacity: 0.85 },
        },
        "glow": {
          "0%, 100%": { boxShadow: "0 0 5px rgba(59, 130, 246, 0.3)" },
          "50%": { boxShadow: "0 0 15px rgba(59, 130, 246, 0.5)" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "pulse-subtle": "pulse-subtle 2s ease-in-out infinite",
        "glow": "glow 2s ease-in-out infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
