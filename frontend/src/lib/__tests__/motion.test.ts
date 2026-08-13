import { describe, expect, it } from "vitest"

import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"
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
  it("has exactly the tiers the CSS tokens declare", () => {
    // There used to be five here and three in CSS, and the two disagreed on
    // the values they shared — JS `base` was 280ms, `--motion-base` is 200ms.
    // A component got a different answer depending on which syntax it was
    // written in. One scale now, and this is what keeps it one.
    expect(Object.keys(MOTION_DURATION).sort()).toEqual(["base", "fast", "panel"])
  })

  it("is in seconds (the motion library's unit), not milliseconds", () => {
    for (const value of Object.values(MOTION_DURATION)) {
      expect(value).toBeGreaterThan(0)
      expect(value).toBeLessThan(1)
    }
  })

  it("ascends: fast < base < panel", () => {
    expect(MOTION_DURATION.fast).toBeLessThan(MOTION_DURATION.base)
    expect(MOTION_DURATION.base).toBeLessThan(MOTION_DURATION.panel)
  })

  it("agrees with the CSS custom properties, to the millisecond", () => {
    // Read the real declarations rather than restating the numbers, so a nudge
    // to `--motion-base` that forgets the JS side fails at the source.
    const css = readFileSync(
      resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "index.css"),
      "utf8",
    )
    const ms = (name: string) => {
      const m = new RegExp(`--motion-${name}:\\s*(\\d+)ms`).exec(css)
      expect(m, `--motion-${name} missing from index.css`).not.toBeNull()
      return Number(m![1])
    }
    expect(MOTION_DURATION.fast * 1000).toBe(ms("fast"))
    expect(MOTION_DURATION.base * 1000).toBe(ms("base"))
    expect(MOTION_DURATION.panel * 1000).toBe(ms("panel"))
  })
})
