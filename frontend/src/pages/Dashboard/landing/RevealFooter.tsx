import { useEffect, useState } from "react"

import Footer from "@/components/layout/Footer"

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
 * AT ONCE. The first version waited for the page to rest at the bottom
 * and for a new gesture, so the momentum that carried a reader to the
 * close could not open it. It read as lag — «не сразу появляется». The
 * footer no longer moves the page, so opening on that momentum costs
 * nothing: any push down at the end brings it up.
 *
 * STILL A FOOTER FOR EVERYONE. It is in the DOM the whole time, so a
 * screen reader and a crawler read it where it always was. Tabbing into
 * it opens it, so a keyboard never lands on a link that is off screen.
 * Under `prefers-reduced-motion` it appears without sliding.
 */
export function RevealFooter() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    // 8px, not 0: the smooth scroller eases into the bottom and spends its
    // last frames a pixel or two short of it.
    const atBottom = () =>
      window.scrollY >= document.documentElement.scrollHeight - window.innerHeight - 8

    const onScroll = () => {
      if (!atBottom()) setOpen(false)
    }

    const onWheel = (event: WheelEvent) => {
      if (event.deltaY < 0) setOpen(false)
      else if (event.deltaY > 0 && atBottom()) setOpen(true)
    }

    let touchStartY: number | null = null
    let touchFromBottom = false
    const onTouchStart = (event: TouchEvent) => {
      touchStartY = event.touches[0]?.clientY ?? null
      touchFromBottom = atBottom()
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
        if (atBottom()) setOpen(true)
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
      {/* A plain band the width of the screen, in the page's own colour — no
          frame, no rounded card («зачем рамка вокруг?»). Only a soft shadow
          upward, so it reads as lying over the close. */}
      <div className="bg-surface shadow-[0_-16px_40px_-28px_hsl(var(--ink)/0.4)]">
        <Footer className="" />
      </div>
    </div>
  )
}
