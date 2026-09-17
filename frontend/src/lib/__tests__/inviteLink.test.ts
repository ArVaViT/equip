/**
 * The accept page reads a token from where new letters put it (the
 * fragment, which no server receives) and from where letters already
 * delivered put it (the query), and sends people back with the fragment.
 */

import { describe, expect, it } from "vitest"
import { inviteAcceptPath, inviteTokenFrom, inviteTokenIsInQuery } from "../inviteLink"

describe("the invitation token in the accept page URL", () => {
  it("is read from the fragment of a new letter", () => {
    const location = { search: "", hash: "#token=abc-123_XYZ" }
    expect(inviteTokenFrom(location)).toBe("abc-123_XYZ")
    expect(inviteTokenIsInQuery(location)).toBe(false)
  })

  it("is still read from the query of a letter sent before the change", () => {
    const location = { search: "?token=abc-123_XYZ", hash: "" }
    expect(inviteTokenFrom(location)).toBe("abc-123_XYZ")
    expect(inviteTokenIsInQuery(location)).toBe(true)
  })

  it("prefers the fragment when both are present", () => {
    expect(inviteTokenFrom({ search: "?token=old", hash: "#token=new" })).toBe("new")
    expect(inviteTokenIsInQuery({ search: "?token=old", hash: "#token=new" })).toBe(false)
  })

  it("is empty when the link carries none", () => {
    expect(inviteTokenFrom({ search: "", hash: "" })).toBe("")
    expect(inviteTokenIsInQuery({ search: "", hash: "" })).toBe(false)
  })

  it("is put back in the fragment, never the query", () => {
    const target = inviteAcceptPath("a b/c")
    expect(target).toEqual({ pathname: "/invite/accept", search: "", hash: "token=a%20b%2Fc" })
    expect(inviteTokenFrom({ search: target.search, hash: `#${target.hash}` })).toBe("a b/c")
  })
})
