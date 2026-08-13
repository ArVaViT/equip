import { describe, expect, it } from "vitest"
import { attemptGate } from "../attemptGate"
import type { QuizAttempt } from "@/types"

const done = (n: number) =>
  Array.from({ length: n }, (_, i) => ({ id: `a${i}`, completed_at: "2026-08-13" }) as QuizAttempt)

describe("attemptGate", () => {
  it("counts only finished attempts", () => {
    const attempts = [...done(2), { id: "open", completed_at: null } as QuizAttempt]
    expect(attemptGate(attempts, 3).used).toBe(2)
  })

  it("closes the gate once the limit is reached", () => {
    expect(attemptGate(done(3), 3).exhausted).toBe(true)
  })

  it("never closes it on an unlimited quiz", () => {
    expect(attemptGate(done(9), null).exhausted).toBe(false)
  })

  it("claims no count when the attempts could not be loaded", () => {
    // `[]` used to stand in for this, which rendered a confident "0 used".
    expect(attemptGate(null, 3).used).toBeNull()
  })

  it("opens on unknown rather than blocking somebody who has attempts left", () => {
    expect(attemptGate(null, 3).exhausted).toBe(false)
  })

  it("but says the count is unverified, so nobody sits an exam they cannot submit", () => {
    // The asymmetry from the chapter lock flips here: there, a guess could
    // deny access; here, a silent guess costs an hour of work.
    expect(attemptGate(null, 3).countUnverified).toBe(true)
  })

  it("stays quiet when there is no limit to be wrong about", () => {
    expect(attemptGate(null, null).countUnverified).toBe(false)
  })
})
