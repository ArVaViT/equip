import { AxiosError } from "axios"
import { describe, expect, it } from "vitest"

import { answerWasLost, newestUnseen } from "../lostResponse"

/**
 * After a lost answer the screen asks the server what it holds. What it
 * takes for «the request's own» decides whether a student is shown their
 * real result, an old one, or told to press again.
 */
describe("answerWasLost", () => {
  it("is only a request with no answer at all", () => {
    expect(answerWasLost(new AxiosError("Network Error", AxiosError.ERR_NETWORK))).toBe(true)
    expect(answerWasLost(new AxiosError("timeout of 30000ms exceeded", AxiosError.ECONNABORTED))).toBe(true)
    const refused = new AxiosError("Bad Request", "ERR_BAD_REQUEST", undefined, undefined, {
      status: 400,
      statusText: "Bad Request",
      data: {},
      headers: {},
      config: { headers: {} } as never,
    })
    expect(answerWasLost(refused)).toBe(false)
    expect(answerWasLost(new Error("Network Error"))).toBe(false)
  })
})

describe("newestUnseen", () => {
  type Row = { id: string; at: string | null }
  const at = (r: Row) => r.at

  it("picks the newest row the screen had not seen", () => {
    const rows: Row[] = [
      { id: "old", at: "2026-08-12T09:00:00Z" },
      { id: "new", at: "2026-08-14T09:00:00Z" },
      { id: "newer", at: "2026-08-14T09:05:00Z" },
    ]
    expect(newestUnseen(rows, new Set(["old"]), at)?.id).toBe("newer")
  })

  it("finds nothing when every row was already on screen", () => {
    const rows: Row[] = [{ id: "a", at: "2026-08-12T09:00:00Z" }]
    expect(newestUnseen(rows, new Set(["a"]), at)).toBeNull()
    expect(newestUnseen([], new Set(), at)).toBeNull()
  })

  it("does not take a row older than the newest the screen held — a screen that keeps only the latest has not seen the history", () => {
    const rows: Row[] = [
      { id: "latest", at: "2026-08-14T09:00:00Z" },
      { id: "earlier", at: "2026-08-12T09:00:00Z" },
    ]
    expect(newestUnseen(rows, new Set(["latest"]), at, "2026-08-14T09:00:00Z")).toBeNull()
    // The resubmission itself is newer than the floor and is found.
    const landed: Row = { id: "sent", at: "2026-08-15T10:00:00Z" }
    expect(newestUnseen([landed, ...rows], new Set(["latest"]), at, "2026-08-14T09:00:00Z")?.id).toBe("sent")
  })

  it("does not place a row without a readable stamp above the floor", () => {
    const rows: Row[] = [{ id: "blank", at: null }]
    expect(newestUnseen(rows, new Set(), at, "2026-08-14T09:00:00Z")).toBeNull()
    // Without a floor an unstamped row is still a row the screen had not seen.
    expect(newestUnseen(rows, new Set(), at)?.id).toBe("blank")
  })
})
