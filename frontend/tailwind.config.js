import tailwindcssAnimate from "tailwindcss-animate"

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    './src/**/*.{ts,tsx}',
  ],
  prefix: "",
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        success: {
          DEFAULT: "hsl(var(--success))",
          foreground: "hsl(var(--success-foreground))",
        },
        warning: {
          DEFAULT: "hsl(var(--warning))",
          foreground: "hsl(var(--warning-foreground))",
        },
        info: {
          DEFAULT: "hsl(var(--info))",
          foreground: "hsl(var(--info-foreground))",
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
        sidebar: {
          DEFAULT: "hsl(var(--sidebar))",
          foreground: "hsl(var(--sidebar-foreground))",
          border: "hsl(var(--sidebar-border))",
          accent: "hsl(var(--sidebar-accent))",
          "accent-foreground": "hsl(var(--sidebar-accent-foreground))",
          ring: "hsl(var(--sidebar-ring))",
        },
        chart: {
          1: "hsl(var(--chart-1))",
          2: "hsl(var(--chart-2))",
          3: "hsl(var(--chart-3))",
          4: "hsl(var(--chart-4))",
          5: "hsl(var(--chart-5))",
        },
        // Visual overhaul v2 — Wave 3. Adds the v2 semantic palette
        // alongside the v1 names so components can opt into the new
        // vocabulary one-by-one. Resolved via tokens-bridge.css today
        // (v1 HSL values); will flip to OKLCH in Wave 9 without
        // touching component code.
        //
        // Naming note: v1 already owns ``accent`` (sage heritage) and
        // ``primary`` (violet). v2's semantic accent (violet, the
        // brand) lands as ``brand`` to avoid the collision. v2's
        // heritage (sage) lands as ``heritage``. ADR-0011.
        surface: {
          DEFAULT: "hsl(var(--color-surface))",
          elevated: "hsl(var(--color-surface-elevated))",
          sunken: "hsl(var(--color-surface-sunken))",
        },
        ink: {
          DEFAULT: "hsl(var(--color-ink))",
          muted: "hsl(var(--color-ink-muted))",
          inverted: "hsl(var(--color-ink-inverted))",
        },
        edge: {
          DEFAULT: "hsl(var(--color-edge))",
          strong: "hsl(var(--color-edge-strong))",
        },
        brand: {
          DEFAULT: "hsl(var(--color-accent))",
          quiet: "hsl(var(--color-accent-quiet))",
          strong: "hsl(var(--color-accent-strong))",
          foreground: "hsl(var(--color-ink-inverted))",
        },
        heritage: {
          DEFAULT: "hsl(var(--color-heritage))",
          quiet: "hsl(var(--color-heritage-quiet))",
        },
      },
      fontFamily: {
        // Literata: Cyrillic drawn by Vera Evstafieva (Modern Cyrillic 2021),
        // variable on opsz 7–72 and wght 200–900, and 233 polytonic Greek
        // glyphs so biblical Greek sets in the same family. Georgia leads the
        // fallback because its x-height/em (.481) is closest to Literata's
        // (.503), so the page barely shifts when the webfont lands.
        serif: ['"Literata Variable"', 'Literata', 'Georgia', 'Cambria', '"Times New Roman"', 'Times', 'serif'],
        // Golos Text: by Alexandra Korolkova (ParaType), commissioned for
        // Russian state services and drawn for continuous screen reading.
        // Replaces Inter, whose Cyrillic is functional but publicly criticised
        // — reverse contrast in Ии Уу к, fractured б, inconsistent descenders
        // in ДЦЩ — and whose own author conceded the extension needed
        // knowledge the project lacked (rsms/inter#567). Golos has no italic
        // and no Greek: both stay in Literata.
        sans: ['"Golos Text Variable"', '"Golos Text"', 'Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      transitionTimingFunction: {
        editorial: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
    },
  },
  plugins: [tailwindcssAnimate],
}
