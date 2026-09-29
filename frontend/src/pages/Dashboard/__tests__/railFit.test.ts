import { describe, expect, it } from "vitest"
import { distributeRail } from "../railFit"

// [verse, calendar, question]
describe("distributeRail", () => {
  it("shares what is left over evenly when everything fits", () => {
    expect(distributeRail([100, 150, 250], 620)).toEqual([140, 190, 290])
  })

  it("gives a missing card nothing and shares among the rest", () => {
    expect(distributeRail([0, 150, 250], 500)).toEqual([0, 200, 300])
  })

  it("takes a shortfall from the calendar first, down to its floor", () => {
    expect(distributeRail([150, 250, 300], 650)).toEqual([150, 200, 300])
    expect(distributeRail([150, 250, 300], 570)).toEqual([150, 120, 300])
  })

  it("then from the question, and the verse last", () => {
    expect(distributeRail([150, 250, 300], 500)).toEqual([150, 120, 230])
    expect(distributeRail([150, 250, 300], 400)).toEqual([120, 120, 160])
  })

  it("never pushes a short card up to its floor", () => {
    expect(distributeRail([150, 80, 300], 480)).toEqual([150, 80, 250])
  })
})
