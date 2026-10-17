import { renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { User } from "@/types"

const reportDetectedTimeZone = vi.fn()
vi.mock("@/services/users", () => ({
  usersService: { reportDetectedTimeZone: (z: string) => reportDetectedTimeZone(z) },
}))

const applyUser = vi.fn()
let currentUser: User | null = null
vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ user: currentUser, applyUser }) }))

let deviceZone = "Europe/Kyiv"
vi.mock("../timeZone", async (orig) => ({
  ...(await orig<typeof import("../timeZone")>()),
  browserTimeZone: () => deviceZone,
}))

import { useTimeZoneSync } from "../useTimeZoneSync"

const base = {
  id: "u1",
  email: "a@b.com",
  full_name: "A",
  avatar_url: null,
  role: "student",
  preferred_locale: "ru",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
} as unknown as User

/**
 * The device zone is reported once, and never over a zone the person chose
 * (2026-09-30 review: a report in flight could land after a choice, and the
 * effect re-sent it on every new user object while it was in flight).
 */
describe("time zone sync", () => {
  beforeEach(() => {
    reportDetectedTimeZone.mockReset()
    applyUser.mockReset()
    deviceZone = "Europe/Kyiv"
  })

  it("reports the device zone once, even if the profile object changes meanwhile", async () => {
    let resolve!: (v: unknown) => void
    reportDetectedTimeZone.mockReturnValue(new Promise((r) => (resolve = r)))
    currentUser = { ...base, time_zone: null, time_zone_source: "default" }
    const { rerender } = renderHook(() => useTimeZoneSync())
    currentUser = { ...currentUser, full_name: "A." }
    rerender()
    expect(reportDetectedTimeZone).toHaveBeenCalledTimes(1)
    expect(reportDetectedTimeZone).toHaveBeenCalledWith("Europe/Kyiv")

    resolve({ id: "u1", time_zone: "Europe/Kyiv", time_zone_source: "detected" })
    await waitFor(() =>
      expect(applyUser).toHaveBeenCalledWith({ id: "u1", time_zone: "Europe/Kyiv", time_zone_source: "detected" }),
    )
  })

  it("applies nothing when the database kept a chosen zone", async () => {
    reportDetectedTimeZone.mockResolvedValue(null)
    currentUser = { ...base, time_zone: "America/Denver", time_zone_source: "detected" }
    renderHook(() => useTimeZoneSync())
    await waitFor(() => expect(reportDetectedTimeZone).toHaveBeenCalledTimes(1))
    await new Promise((r) => setTimeout(r, 0))
    expect(applyUser).not.toHaveBeenCalled()
  })

  it("never reports over a chosen zone", () => {
    currentUser = { ...base, time_zone: "America/Denver", time_zone_source: "chosen" }
    renderHook(() => useTimeZoneSync())
    expect(reportDetectedTimeZone).not.toHaveBeenCalled()
  })

  it("writes nothing for a closed account, which the profile trigger would refuse", () => {
    currentUser = { ...base, time_zone: null, time_zone_source: "default", deleted_at: "2026-10-16T00:00:00Z", deactivated_at: "2026-10-16T00:00:00Z" }
    renderHook(() => useTimeZoneSync())
    expect(reportDetectedTimeZone).not.toHaveBeenCalled()
  })

  // 2026-10-17: 42 of 48 profiles had no zone at all (time_zone_source=default).
  it.each(["UTC", "Etc/UTC", "Etc/GMT"])("records nothing when the browser only says %s", (zone) => {
    deviceZone = zone
    currentUser = { ...base, time_zone: null, time_zone_source: "default" }
    renderHook(() => useTimeZoneSync())
    expect(reportDetectedTimeZone).not.toHaveBeenCalled()
  })

  it("confirms a zone that is right but still marked default", async () => {
    reportDetectedTimeZone.mockResolvedValue({ id: "u1", time_zone: "Europe/Kyiv", time_zone_source: "detected" })
    currentUser = { ...base, time_zone: "Europe/Kyiv", time_zone_source: "default" }
    renderHook(() => useTimeZoneSync())
    await waitFor(() => expect(reportDetectedTimeZone).toHaveBeenCalledWith("Europe/Kyiv"))
  })

  it("leaves a detected zone alone while the device agrees", () => {
    currentUser = { ...base, time_zone: "Europe/Kyiv", time_zone_source: "detected" }
    renderHook(() => useTimeZoneSync())
    expect(reportDetectedTimeZone).not.toHaveBeenCalled()
  })

  it("follows the device to a new place when the zone was only detected", async () => {
    deviceZone = "America/Indiana/Indianapolis"
    reportDetectedTimeZone.mockResolvedValue({ id: "u1", time_zone: deviceZone, time_zone_source: "detected" })
    currentUser = { ...base, time_zone: "Europe/Kyiv", time_zone_source: "detected" }
    renderHook(() => useTimeZoneSync())
    await waitFor(() => expect(reportDetectedTimeZone).toHaveBeenCalledWith("America/Indiana/Indianapolis"))
  })
})
