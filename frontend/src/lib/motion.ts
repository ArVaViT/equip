/**
 * Shared motion tokens — single source of truth for animation timing and easing
 * across the app. Keeps editorial feel consistent everywhere: page transitions,
 * card hovers, fade-ins, reveal scrolls, hero blocks all use the same curve.
 *
 * Why a constant, not a Tailwind utility:
 * - `framer-motion`/`motion` `transition.ease` accepts a cubic-bezier tuple,
 *   not a CSS string. Tailwind's `ease-editorial` covers the CSS side; this
 *   covers the JS side. Both encode the same curve so a hover-in-CSS and a
 *   layout-shift-in-JS feel like one system.
 *
 * Curve: `[0.22, 1, 0.36, 1]` — "easeOutQuint"-ish. Quick start, gentle settle.
 * Reads as confident, never bouncy. Matches the print-leaning visual language.
 */
export const EDITORIAL_EASE = [0.22, 1, 0.36, 1] as const

/**
 * Standard durations (seconds — `motion` defaults to seconds, not ms).
 * Use these instead of inline literals so timing reads as a system, not noise.
 *
 * - `instant`  — color/state changes that should feel immediate (0.12s)
 * - `fast`     — small affordances: press, hover-color, focus ring (0.2s)
 * - `base`     — most state changes (0.28s) — this is the default
 * - `entrance` — list/card initial reveals (0.48s)
 * - `slow`     — hero/large-block reveals (0.55s)
 */
export const MOTION_DURATION = {
  instant: 0.12,
  fast: 0.2,
  base: 0.28,
  entrance: 0.48,
  slow: 0.55,
} as const
