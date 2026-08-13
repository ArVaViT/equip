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
          // The step for text sitting on this token's own tint — see the
          // chip-step note in index.css. Never the DEFAULT: that pairing is
          // the one axe failed us on.
          ink: "hsl(var(--destructive-ink))",
        },
        success: {
          DEFAULT: "hsl(var(--success))",
          foreground: "hsl(var(--success-foreground))",
          // The step for text sitting on this token's own tint — see the
          // chip-step note in index.css. Never the DEFAULT: that pairing is
          // the one axe failed us on.
          ink: "hsl(var(--success-ink))",
        },
        warning: {
          DEFAULT: "hsl(var(--warning))",
          foreground: "hsl(var(--warning-foreground))",
          // The step for text sitting on this token's own tint — see the
          // chip-step note in index.css. Never the DEFAULT: that pairing is
          // the one axe failed us on.
          ink: "hsl(var(--warning-ink))",
        },
        info: {
          DEFAULT: "hsl(var(--info))",
          foreground: "hsl(var(--info-foreground))",
          // The step for text sitting on this token's own tint — see the
          // chip-step note in index.css. Never the DEFAULT: that pairing is
          // the one axe failed us on.
          ink: "hsl(var(--info-ink))",
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
          ink: "hsl(var(--brand-ink))",
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
      // The ladder, measured against pages that are actually good rather than
      // against a ratio picked from a generator.
      //
      // What looking at apple.com actually showed (measured, 2026-08-12): nine
      // distinct sizes on the whole homepage and sixteen distinct
      // size/weight/line-height/tracking combinations — and *72% of its text
      // nodes are 14px or smaller*, almost exactly our own 85%. So «everything
      // is too small» was the wrong diagnosis. Apple's 12px is footer and
      // legal furniture; what it also has, and we do not, is a content ladder:
      // 17 body → 21 deck → 24 tile → 34/40/56 headline, each size arriving
      // with the line-height and tracking that belong to it.
      //
      // Ours jumped from 14 straight to 24 with almost nothing between —
      // `text-base` 29 uses, `text-lg` 18, `text-xl` 18 against `text-sm` 306.
      // That gap is what reads as an admin tool, not the floor.
      //
      // Tracking stays mild at the top: Cyrillic is denser and more
      // rectangular than Latin, and the aggressive negative tracking that
      // flatters English display type closes Russian counters up.
      fontSize: {
        // Furniture: captions, verse references, legal. Replaces the 46
        // hardcoded uses of text-[10px] and text-[11px], which were below the
        // floor at which Cyrillic stays legible on a mid-range phone.
        xs: ["0.75rem", { lineHeight: "1rem" }],
        // Meta, secondary, dense table cells.
        sm: ["0.875rem", { lineHeight: "1.25rem" }],
        // Body. The step that was missing: 17px, not 16, with the leading a
        // Cyrillic paragraph needs.
        base: ["1.0625rem", { lineHeight: "1.625rem", letterSpacing: "-0.006em" }],
        // Deck / lead-in. This is the rung that did not exist.
        lg: ["1.3125rem", { lineHeight: "1.875rem", letterSpacing: "-0.011em" }],
        // Card and tile titles.
        xl: ["1.5rem", { lineHeight: "1.875rem", letterSpacing: "-0.014em" }],
        "2xl": ["1.75rem", { lineHeight: "2.125rem", letterSpacing: "-0.016em" }],
        "3xl": ["2.125rem", { lineHeight: "2.5rem", letterSpacing: "-0.019em" }],
        "4xl": ["2.625rem", { lineHeight: "2.875rem", letterSpacing: "-0.021em" }],
        "5xl": ["3.25rem", { lineHeight: "3.5rem", letterSpacing: "-0.023em" }],
        // Long-form: chapters, essays, anything somebody reads rather than
        // scans. Anthropic sets its articles at 17px/1.55 in 640px, which
        // measured out at 68 characters per line — in Cyrillic, checked.
        // Ours goes slightly larger and slightly looser because Russian
        // lowercase has fewer ascenders and descenders and needs the air.
        reading: ["1.125rem", { lineHeight: "1.7" }],
      },
      transitionDuration: {
        // The three durations, reachable as duration-fast / -base / -panel so
        // a component never has to invent 250ms.
        fast: "var(--motion-fast)",
        base: "var(--motion-base)",
        panel: "var(--motion-panel)",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      transitionTimingFunction: {
        // `editorial` predates the token pass and is kept: it is on 40-odd
        // components and is close enough to --ease-out that swapping it in one
        // go would be churn without a visible gain. New work uses out/in-out.
        editorial: "cubic-bezier(0.22, 1, 0.36, 1)",
        out: "var(--ease-out)",
        "in-out": "var(--ease-in-out)",
      },
    },
  },
  plugins: [tailwindcssAnimate],
}
