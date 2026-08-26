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
      fontFamily: {
        sans: ['Karla', 'system-ui', 'sans-serif'],
        heading: ['Karla', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Menlo', 'monospace'],
        /* The brand triad. `sans`/`heading` stay on Karla until Track 5
         * migrates the shell, so type does not shift under the current UI. */
        display: ['Fraunces', 'DM Serif Display', 'Georgia', 'serif'],
        grotesk: ['Space Grotesk', 'Plus Jakarta Sans', 'system-ui', 'sans-serif'],
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
          warning: "var(--color-status-warning)",
          "warning-bg": "var(--color-status-warning-bg)",
          critical: "var(--color-status-critical)",
          "critical-bg": "var(--color-status-critical-bg)",
          telemetry: "var(--color-status-telemetry)",
          "telemetry-bg": "var(--color-status-telemetry-bg)",
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
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
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
