import { useCallback, useEffect, useRef } from "react"

/**
 * Only the newest request may write its answer.
 *
 * A loader that is a `useCallback` re-run on its deps (and by a «Try again»
 * button) has no cancel flag of its own: switch a filter twice quickly and the
 * first, slower response lands last and overwrites the second. Ten screens
 * had exactly that race (2026-10-03). `useAsyncData` solves it for loaders
 * that fit its shape; this is the same guarantee for the ones that keep their
 * own state.
 *
 *   const begin = useLatestRequest()
 *   const load = useCallback(async () => {
 *     const isCurrent = begin()
 *     const data = await fetchSomething()
 *     if (!isCurrent()) return
 *     setData(data)
 *   }, [begin, …])
 *
 * Unmounting retires every request in flight.
 */
export function useLatestRequest(): () => () => boolean {
  const seq = useRef(0)
  useEffect(
    () => () => {
      seq.current += 1
    },
    [],
  )
  return useCallback(() => {
    seq.current += 1
    const mine = seq.current
    return () => mine === seq.current
  }, [])
}
