import { useEffect, useState } from "react"

type Side = "left" | "right"

/**
 * Picks ``left-0`` or ``right-0`` for an absolutely-positioned menu
 * panel based on where the trigger sits in the viewport. Without
 * this, dropdowns anchored to right-edge toolbar buttons overflow
 * past the right viewport edge — the user sees a clipped or
 * scroll-required menu.
 *
 * We measure on open + on resize, and only once (the trigger doesn't
 * move while open in our toolbar). Returns the Tailwind class to
 * apply on the panel; the trigger ref is what's measured.
 */
export function useDropdownPosition(
  open: boolean,
  triggerRef: React.RefObject<HTMLElement | null>,
  /** Approximate menu width in pixels — used to predict overflow. Pick
   * the same number as the panel's ``w-*`` tailwind class so the
   * heuristic matches reality. */
  menuWidthPx: number,
): { side: Side; alignClass: string } {
  const [side, setSide] = useState<Side>("left")

  useEffect(() => {
    if (!open || !triggerRef.current) return
    const measure = () => {
      const rect = triggerRef.current?.getBoundingClientRect()
      if (!rect) return
      const viewportWidth = window.innerWidth
      // ``rect.left`` is the left edge of the trigger. The menu opens
      // anchored to that edge by default, which means its right edge
      // lands at ``rect.left + menuWidthPx``. If that exceeds the
      // viewport, flip the anchor to the trigger's right edge instead
      // (panel grows leftwards, fits inside the viewport).
      const wouldOverflow = rect.left + menuWidthPx > viewportWidth - 8
      setSide(wouldOverflow ? "right" : "left")
    }
    measure()
    window.addEventListener("resize", measure)
    return () => window.removeEventListener("resize", measure)
  }, [open, triggerRef, menuWidthPx])

  return {
    side,
    alignClass: side === "left" ? "left-0" : "right-0",
  }
}
