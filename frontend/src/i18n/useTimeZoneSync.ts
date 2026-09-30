import { useEffect } from "react"

import { useAuth } from "@/context/useAuth"
import { usersService } from "@/services/users"

import { browserTimeZone, isValidTimeZone } from "./timeZone"

/**
 * Keep the profile's zone in step with the device until the person picks one.
 *
 * The profile records the zone so the server can use it too (an email that
 * says when a lesson starts). Until someone chooses a zone on the profile
 * page, it follows the device — a teacher who flies from Indiana to Kyiv sees
 * Kyiv time without touching a setting. Once chosen, nothing automatic
 * overwrites it (same rule as `locale_source`).
 */
export function useTimeZoneSync(): void {
  const { user, applyUser } = useAuth()

  useEffect(() => {
    if (!user) return
    if (user.time_zone_source === "chosen") return
    const device = browserTimeZone()
    if (!isValidTimeZone(device) || device === user.time_zone) return
    let cancelled = false
    usersService
      .updateProfile({ time_zone: device, time_zone_source: "detected" })
      .then((profile) => {
        if (!cancelled) applyUser({ ...user, time_zone: profile.time_zone ?? device, time_zone_source: "detected" })
      })
      // Best effort: display already follows the device; the next load retries.
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [user, applyUser])
}
