import { useEffect, useState } from "react"

/**
 * The current time, re-read every `intervalMs` — for the parts of a page
 * that change with the clock ("in 12 minutes", "on now", "Join" lighting
 * up). Paused while the tab is hidden; brought up to date when it returns.
 */
export function useNow(intervalMs = 30_000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const tick = () => setNow(Date.now())
    const id = window.setInterval(() => {
      if (document.visibilityState !== "hidden") tick()
    }, intervalMs)
    document.addEventListener("visibilitychange", tick)
    return () => {
      window.clearInterval(id)
      document.removeEventListener("visibilitychange", tick)
    }
  }, [intervalMs])
  return now
}
