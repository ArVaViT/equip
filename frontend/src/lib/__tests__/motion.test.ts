import { describe, expect, it } from "vitest"

import { EDITORIAL_EASE, MOTION_DURATION } from "@/lib/motion"

/**
 * Shared motion tokens are imported across page transitions, card
 * hovers, fade-ins, reveal scrolls — anywhere the JS side of motion
 * needs to match the CSS ``ease-editorial`` curve. The values are
 * load-bearing for visual consistency, so a typo / accidental rename
 * would scatter the look-and-feel without triggering any lint or type
 * error.
 *
 * Tests pin the shape and values so a refactor that, say, drops a
 * duration tier or changes the curve coefficients shows up
 * immediately in CI.
 */

describe("EDITORIAL_EASE", () => {
  it("is the canonical 'easeOutQuint'-ish cubic-bezier", () => {
    expect(Array.from(EDITORIAL_EASE)).toEqual([0.22, 1, 0.36, 1])
  })

  it("matches the cubic-bezier(4-tuple) shape framer/motion expects", () => {
    expect(EDITORIAL_EASE.length).toBe(4)
    for (const n of EDITORIAL_EASE) {
      expect(typeof n).toBe("number")
      expect(Number.isFinite(n)).toBe(true)
    }
  })

  it("starts and ends inside the [0, 1] cubic-bezier control range", () => {
    // The X coordinates of a cubic-bezier ease MUST be in [0, 1] for
    // CSS / framer-motion compatibility — otherwise the timing
    // function is invalid. Y can exceed (overshoot / undershoot) but
    // this curve doesn't.
    expect(EDITORIAL_EASE[0]).toBeGreaterThanOrEqual(0)
    expect(EDITORIAL_EASE[0]).toBeLessThanOrEqual(1)
    expect(EDITORIAL_EASE[2]).toBeGreaterThanOrEqual(0)
    expect(EDITORIAL_EASE[2]).toBeLessThanOrEqual(1)
  })
})

describe("MOTION_DURATION", () => {
  it("exposes the five canonical tiers", () => {
    expect(Object.keys(MOTION_DURATION).sort()).toEqual(
      ["base", "entrance", "fast", "instant", "slow"].sort(),
    )
  })

  it("is in seconds (matches motion library default unit), not milliseconds", () => {
    // Every tier should be < 1s — anything in the ms range would
    // surface as 10+ seconds of motion in the actual library, which
    // would be wildly wrong.
    for (const value of Object.values(MOTION_DURATION)) {
      expect(value).toBeGreaterThan(0)
      expect(value).toBeLessThan(1)
    }
  })

  it("tiers ascend in duration (instant < fast < base < entrance < slow)", () => {
    expect(MOTION_DURATION.instant).toBeLessThan(MOTION_DURATION.fast)
    expect(MOTION_DURATION.fast).toBeLessThan(MOTION_DURATION.base)
    expect(MOTION_DURATION.base).toBeLessThan(MOTION_DURATION.entrance)
    expect(MOTION_DURATION.entrance).toBeLessThan(MOTION_DURATION.slow)
  })

  it("locks in the exact values (regression guard)", () => {
    expect(MOTION_DURATION).toEqual({
      instant: 0.12,
      fast: 0.2,
      base: 0.28,
      entrance: 0.48,
      slow: 0.55,
    })
  })
})
