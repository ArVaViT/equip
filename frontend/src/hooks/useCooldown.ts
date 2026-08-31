import { useCallback, useEffect, useRef, useState } from "react"

/**
 * Seconds left before an action may be repeated.
 *
 * Supabase refuses a second email to the same address inside
 * `smtp_max_frequency` (60s) with a 429 the reader cannot interpret, so every
 * screen that offers "send it again" counts down rather than letting somebody
 * hammer the button into an error.
 *
 * Starts running immediately: the first email left a moment ago, so the
 * button is never offered at a time the server would refuse it anyway.
 */
export function useCooldown(seconds: number): { remaining: number; restart: () => void } {
  const [remaining, setRemaining] = useState(seconds)
  const timer = useRef<ReturnType<typeof setInterval>>()

  useEffect(() => {
    timer.current = setInterval(() => {
      setRemaining((left) => (left <= 1 ? 0 : left - 1))
    }, 1000)
    return () => clearInterval(timer.current)
  }, [])

  const restart = useCallback(() => setRemaining(seconds), [seconds])

  return { remaining, restart }
}
