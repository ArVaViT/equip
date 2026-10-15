import { useCallback, useSyncExternalStore } from "react"

/**
 * Whether a CSS media query matches, kept in step with the window.
 *
 * For a layout CSS alone cannot switch — a table and a list are different
 * elements, not different styles. Without `matchMedia` (tests, old engines)
 * the answer is `false`, so callers should name the query for the wider
 * layout and treat the narrow one as the default.
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (typeof window === "undefined" || !window.matchMedia) return () => {}
      const list = window.matchMedia(query)
      list.addEventListener("change", onChange)
      return () => list.removeEventListener("change", onChange)
    },
    [query],
  )
  const current = () =>
    typeof window !== "undefined" && !!window.matchMedia && window.matchMedia(query).matches
  return useSyncExternalStore(subscribe, current, () => false)
}
