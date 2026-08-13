/**
 * The JS half of the motion system, and only the half CSS cannot do.
 *
 * `motion`/framer takes a cubic-bezier as a tuple, not a CSS string, so a
 * layout animation cannot read `--ease-out` the way a `transition-` class can.
 * That is the entire reason this file exists.
 *
 * `MOTION_DURATION` used to have five keys — `instant` 0.12, `fast` 0.2,
 * `base` 0.28, `entrance` 0.48, `slow` 0.55 — and the CSS side has three:
 * `--motion-fast` 120ms, `--motion-base` 200ms, `--motion-panel` 400ms. Two
 * scales, disagreeing on both the number of steps and the values of the ones
 * they shared: JS `base` was 280ms, CSS `base` was 200ms. A component picked
 * whichever syntax it happened to be written in and got a different answer.
 * `slow` had no callers at all.
 *
 * Three durations now, the same three the CSS tokens declare, in the seconds
 * `motion` expects. One scale, two syntaxes, no third opinion.
 */

/**
 * Quick start, gentle settle — "easeOutQuint"-ish. Reads as confident, never
 * bouncy. The CSS twin is `--ease-out`, and they must stay identical: a hover
 * in CSS and a layout shift in JS on the same element should feel like one
 * thing.
 */
export const EDITORIAL_EASE = [0.22, 1, 0.36, 1] as const

/**
 * Seconds, because `motion` defaults to seconds while CSS defaults to
 * milliseconds. The values mirror `--motion-fast` / `--motion-base` /
 * `--motion-panel` exactly; `motion.test.ts` fails if they drift.
 *
 * - `fast`  (120ms) — micro-feedback: press, hover, colour
 * - `base`  (200ms) — interaction: menus, popovers, state changes
 * - `panel` (400ms) — panels, sheets, route-level movement
 */
export const MOTION_DURATION = {
  fast: 0.12,
  base: 0.2,
  panel: 0.4,
} as const
