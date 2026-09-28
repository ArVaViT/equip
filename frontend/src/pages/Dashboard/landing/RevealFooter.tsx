import { useEffect, useState } from "react"

import Footer from "@/components/layout/Footer"

/** A new wheel gesture starts after this long without wheel events. */
const GESTURE_GAP_MS = 200
/** How long the page must have rested at the bottom before a push counts. */
const SETTLED_MS = 250
/** A swipe this long, in px, is an intent rather than a wobble. */
const SWIPE_PX = 24

/**
 * The footer, brought up by one more scroll at the end of the page.
 *
 * It used to sit in the flow under the close. The close is a full screen
 * and a rest stop, so reaching the legal links took one more scroll that
 * moved the whole page: «Ready to start?» slid up out of its clearing and
 * across the deck of leaves behind it — the words and the scene mixed —
 * only to show a strip of small print. Vadym: «на последнем скроле будем
 * делать не чтоб скрол срабатывал, а чтоб футер выскакивал».
 *
 * So the page now ends on the close, and the footer is a sheet fixed to
 * the bottom edge, out of sight. Pushing past the end — a wheel, a swipe,
 * PageDown, Space, the down arrow, End — slides it up over the bottom of
 * the close, which stays exactly where it is. Any way back up — the wheel,
 * a swipe down, PageUp, Escape, or the page scrolling away — puts it back.
 *
 * NOT ON THE WAY IN. The gesture that carries a reader to the close keeps
 * firing wheel events after the page has stopped (a trackpad's momentum
 * runs for a second or more). Counting those would open the footer the
 * moment the close arrives, which is the very jump this replaces. A push
 * counts only when the page has been at the bottom for `SETTLED_MS` and the
 * wheel event starts a new gesture; a swipe counts only if it started at
 * the bottom.
 *
 * STILL A FOOTER FOR EVERYONE. It is in the DOM the whole time, so a
 * screen reader and a crawler read it where it always was. Tabbing into
 * it opens it, so a keyboard never lands on a link that is off screen.
 * Under `prefers-reduced-motion` it appears without sliding.
 */
export function RevealFooter() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const atBottom = () =>
      window.scrollY >= document.documentElement.scrollHeight - window.innerHeight - 2
    let bottomSince = atBottom() ? performance.now() : Number.POSITIVE_INFINITY
    const settled = () => atBottom() && performance.now() - bottomSince > SETTLED_MS

    const onScroll = () => {
      if (atBottom()) {
        if (bottomSince === Number.POSITIVE_INFINITY) bottomSince = performance.now()
        return
      }
      bottomSince = Number.POSITIVE_INFINITY
      setOpen(false)
    }

    let lastWheelAt = 0
    const onWheel = (event: WheelEvent) => {
      const now = performance.now()
      const newGesture = now - lastWheelAt > GESTURE_GAP_MS
      lastWheelAt = now
      if (event.deltaY < 0) setOpen(false)
      else if (event.deltaY > 0 && newGesture && settled()) setOpen(true)
    }

    let touchStartY: number | null = null
    let touchFromBottom = false
    const onTouchStart = (event: TouchEvent) => {
      touchStartY = event.touches[0]?.clientY ?? null
      touchFromBottom = settled()
    }
    const onTouchMove = (event: TouchEvent) => {
      const y = event.touches[0]?.clientY
      if (touchStartY === null || y === undefined) return
      const pushed = touchStartY - y
      if (pushed > SWIPE_PX && touchFromBottom) setOpen(true)
      else if (pushed < -SWIPE_PX) setOpen(false)
    }

    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (target?.closest("input, textarea, select, [contenteditable='true']")) return
      if (["PageDown", " ", "ArrowDown", "End"].includes(event.key)) {
        if (settled()) setOpen(true)
      } else if (["PageUp", "ArrowUp", "Home", "Escape"].includes(event.key)) {
        setOpen(false)
      }
    }

    window.addEventListener("scroll", onScroll, { passive: true })
    window.addEventListener("wheel", onWheel, { passive: true })
    window.addEventListener("touchstart", onTouchStart, { passive: true })
    window.addEventListener("touchmove", onTouchMove, { passive: true })
    window.addEventListener("keydown", onKeyDown)
    return () => {
      window.removeEventListener("scroll", onScroll)
      window.removeEventListener("wheel", onWheel)
      window.removeEventListener("touchstart", onTouchStart)
      window.removeEventListener("touchmove", onTouchMove)
      window.removeEventListener("keydown", onKeyDown)
    }
  }, [])

  return (
    <div
      data-state={open ? "open" : "closed"}
      onFocus={() => setOpen(true)}
      className={
        "fixed inset-x-0 bottom-0 z-40 transition-transform duration-panel ease-out motion-reduce:transition-none " +
        (open ? "translate-y-0" : "translate-y-full")
      }
    >
      {/* A sheet, not a band: rounded at the top, a handle, a shadow cast
          upward — the shape a phone already knows means «pulled up from
          below». Opaque, because it lies over the close and the scene. */}
      <div className="mx-auto max-w-6xl rounded-t-2xl border border-b-0 border-line bg-surface shadow-[0_-18px_48px_-24px_hsl(var(--ink)/0.35)]">
        <span aria-hidden className="mx-auto mt-2 block h-1 w-8 rounded-full bg-line" />
        <Footer className="" />
      </div>
    </div>
  )
}
