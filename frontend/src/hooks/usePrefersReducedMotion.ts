import { useSyncExternalStore } from "react"

const QUERY = "(prefers-reduced-motion: reduce)"

function subscribe(onChange: () => void): () => void {
  if (typeof window === "undefined" || !window.matchMedia) return () => {}
  const list = window.matchMedia(QUERY)
  list.addEventListener("change", onChange)
  return () => list.removeEventListener("change", onChange)
}

function current(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia && window.matchMedia(QUERY).matches
}

/**
 * The reader's "reduce motion" setting, without the animation library's hook —
 * so a page that only needs to know can skip 38 KB (gzip) of JavaScript.
 */
export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, current, () => false)
}
