import { useEffect, useState } from "react"
import { zonedDayKey } from "./timeZone"

/** How often an open page looks at the clock. The day is all it needs. */
const CHECK_EVERY_MS = 60_000

/**
 * `YYYY-MM-DD` of today on the reader's calendar, which changes when the
 * reader's midnight passes. A value read once at mount kept yesterday on a
 * tab left open overnight. A laptop that slept past midnight is caught when
 * the tab is shown again, since timers do not run while it sleeps.
 */
export function useZonedTodayKey(): string {
  const [key, setKey] = useState(() => zonedDayKey(new Date()))
  useEffect(() => {
    const check = () => setKey(zonedDayKey(new Date()))
    const timer = window.setInterval(check, CHECK_EVERY_MS)
    document.addEventListener("visibilitychange", check)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener("visibilitychange", check)
    }
  }, [])
  return key
}
