import { useEffect, useRef } from "react"

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
 * overwrites it (same rule as `locale_source`): not on the client, and not in
 * the database either, where the write itself refuses a chosen row — a
 * choice made while this report is in flight wins whichever lands first.
 *
 * One report per person and device zone: a re-render while it is in flight
 * does not send it again.
 */
export function useTimeZoneSync(): void {
  const { user, applyUser } = useAuth()
  const reported = useRef<string | null>(null)
  const latest = useRef(user)
  useEffect(() => {
    latest.current = user
  })

  useEffect(() => {
    if (!user) return
    if (user.time_zone_source === "chosen") return
    const device = browserTimeZone()
    if (!isValidTimeZone(device) || device === user.time_zone) return
    const key = `${user.id}:${device}`
    if (reported.current === key) return
    reported.current = key
    const id = user.id
    usersService
      .reportDetectedTimeZone(device)
      .then((profile) => {
        // Nothing written: the row already holds a chosen zone.
        if (!profile) return
        // Chosen here since the report left: the choice stands.
        if (latest.current?.time_zone_source === "chosen") return
        applyUser({ id, time_zone: profile.time_zone ?? device, time_zone_source: "detected" })
      })
      // Best effort: display already follows the device; the next load retries.
      .catch(() => {
        reported.current = null
      })
  }, [user, applyUser])
}
