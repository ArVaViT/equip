import Lenis from "lenis"
import "lenis/dist/lenis.css"

import { registerScroller } from "./scrollControl"

/**
 * How the landing page scrolls on a desktop: a little weight, and a pause at
 * every scene.
 *
 * Vadym, pointing at claude.com/product: «на каждом блоке человек
 * задерживается и случайно не проскальзывает ниже чем нужно, чтоб
 * экспириенс был максимально прикольным». Two things produce that on their
 * page, and this file is both of them.
 *
 * 1. WEIGHT. Lenis turns the wheel's steps into one continuous glide. It is
 *    what claude.com runs, and it is most of why their page feels heavy and
 *    ours felt like a document. Wheel only: touch keeps the phone's own
 *    physics (`syncTouch` off), and this whole module is only loaded where
 *    the backdrop is — desktop, motion allowed.
 *
 * 2. A PAUSE AT EVERY SCENE. Each scene marks where a reader should come to
 *    rest with `data-scene-stop` — `top` for the hero, `start` for each of
 *    the three claims, `center` for the tour, the shelf, the close and the
 *    film, `end` for the bottom of the page. Two rules use those marks:
 *
 *    - THE WALL. A wheel gesture that would carry the page *across* a stop
 *      is ended on it. Further wheel input in the same direction is held
 *      until the gesture ends (the stream of wheel events pauses) or for at
 *      most `WALL_HOLD_MS`, whichever comes first — so a trackpad's
 *      momentum cannot fling the reader two scenes down, and nobody is ever
 *      held longer than a beat. Reversing direction releases it at once.
 *
 *    - THE SETTLE. A reader who stops *near* a stop, heading towards it, is
 *      carried the rest of the way — so a video is never left cut in half
 *      by the bottom edge. It only ever pulls forward, in the direction of
 *      travel, plus a small allowance for overshoot. It never drags anyone
 *      back up the page to where they were a second ago.
 *
 * 3. THE KEYBOARD. PageDown, PageUp and Space move one scene, not one
 *    screen — a screen is an arbitrary distance on a page whose scenes are
 *    screens of their own, and it left the reader between two of them.
 *    Arrows and Home/End keep their native meaning, and nothing is taken
 *    while focus is in a field.
 *
 * WHY NOT CSS `scroll-snap-type: y proximity`. It was the first version and
 * it trapped the page on the hero: every wheel notch (~100px) ended nearer
 * to the hero's snap point than to the next one ~800px down, so Chrome
 * snapped straight back, notch after notch. Proximity snapping has no idea
 * of direction; these two rules are nothing but direction.
 *
 * Returns the cleanup.
 */

/** Longest a wall may hold a gesture that keeps pushing, in ms. */
const WALL_HOLD_MS = 650
/** A gap this long in wheel events means the gesture has ended. */
const GESTURE_GAP_MS = 180
/** How far ahead of a stop a settle will reach, as a share of the viewport. */
const SETTLE_AHEAD = 0.35
/** How far past a stop still counts as overshoot to correct. */
const SETTLE_BEHIND = 0.06

const easeOutCubic = (t: number) => 1 - (1 - t) ** 3

function readStops(): number[] {
  const vh = window.innerHeight
  const limit = Math.max(0, document.documentElement.scrollHeight - vh)
  const stops = [...document.querySelectorAll<HTMLElement>("[data-scene-stop]")].map((el) => {
    const rect = el.getBoundingClientRect()
    const top = rect.top + window.scrollY
    switch (el.dataset.sceneStop) {
      case "top":
        return 0
      case "center":
        return top + rect.height / 2 - vh / 2
      case "end":
        return limit
      default:
        return top
    }
  })
  return [...new Set(stops.map((s) => Math.round(Math.min(limit, Math.max(0, s)))))].sort(
    (a, b) => a - b,
  )
}

export default function startPageScroll(): () => void {
  const lenis = new Lenis({
    // Lower is heavier. Lenis's default is 0.1; a touch under it reads as
    // weight without the page lagging behind the hand.
    lerp: 0.085,
    smoothWheel: true,
    syncTouch: false,
    // Hash links still land where they point.
    anchors: true,
    virtualScroll: (data) => wall(data.deltaY, data.event),
  })

  const glideTo = (y: number) =>
    lenis.scrollTo(y, { duration: 0.9, easing: easeOutCubic })
  registerScroller({ scrollTo: glideTo })

  // ── the wall ─────────────────────────────────────────────────────────
  let held: { stop: number; direction: 1 | -1; since: number } | null = null
  let lastWheelAt = 0
  let lastDirection: 1 | -1 = 1
  // What moved the page last. A settle follows the wheel only: a drag of
  // the scrollbar or a keyboard jump is a reader choosing an exact spot.
  // Tracked as the last input rather than as "a wheel event within N ms",
  // because a long glide outlasts any N — at lerp 0.085 a 700px flick is
  // still moving 1.5s after the last wheel event, and a time window made
  // the settle give up on exactly the flicks it exists for.
  let lastInput: "wheel" | "other" = "other"
  const onOtherInput = () => {
    lastInput = "other"
  }

  function wall(deltaY: number, event: WheelEvent | TouchEvent): boolean {
    if (!event.type.includes("wheel") || deltaY === 0) return true
    const now = performance.now()
    const direction: 1 | -1 = deltaY > 0 ? 1 : -1
    const sincePrevious = now - lastWheelAt
    lastWheelAt = now
    lastInput = "wheel"
    window.clearTimeout(gestureEnd)
    gestureEnd = window.setTimeout(settle, GESTURE_GAP_MS)
    lastDirection = direction

    if (held) {
      const release =
        direction !== held.direction ||
        sincePrevious > GESTURE_GAP_MS ||
        now - held.since > WALL_HOLD_MS
      if (!release) {
        if (event.cancelable) event.preventDefault()
        return false
      }
      held = null
    }

    const from = lenis.targetScroll
    const to = from + deltaY
    const crossed = readStops().find((stop) =>
      direction > 0 ? stop > from + 1 && stop < to : stop < from - 1 && stop > to,
    )
    if (crossed === undefined) return true

    if (event.cancelable) event.preventDefault()
    held = { stop: crossed, direction, since: now }
    lenis.scrollTo(crossed, { programmatic: false, lerp: 0.1 })
    return false
  }

  // ── the settle ───────────────────────────────────────────────────────
  // Decided the moment the gesture ends, against where the glide is going
  // to stop (`targetScroll`), not after it has stopped. Waiting for the page
  // to come to rest made it two motions — a long glide, a pause, then a
  // second glide onto the scene. Retargeting the glide in flight makes it
  // one: the page simply lands on the scene.
  let gestureEnd = 0
  const settle = () => {
    if (lastInput !== "wheel" || held) return
    const y = lenis.targetScroll
    const vh = window.innerHeight
    const ahead = vh * SETTLE_AHEAD
    const behind = vh * SETTLE_BEHIND
    let best: number | null = null
    for (const stop of readStops()) {
      const offset = (stop - y) * lastDirection
      if (offset > ahead || offset < -behind || Math.abs(stop - y) < 2) continue
      if (best === null || Math.abs(stop - y) < Math.abs(best - y)) best = stop
    }
    if (best !== null) lenis.scrollTo(best, { programmatic: false, lerp: 0.085 })
  }

  // ── the keyboard ─────────────────────────────────────────────────────
  const onKey = (event: KeyboardEvent) => {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return
    const target = event.target as HTMLElement | null
    if (target?.closest("input, textarea, select, [contenteditable], video, [role=slider]")) return
    const forward =
      event.key === "PageDown" || (event.key === " " && !event.shiftKey)
    const backward =
      event.key === "PageUp" || (event.key === " " && event.shiftKey)
    if (!forward && !backward) return
    const y = lenis.targetScroll
    const stops = readStops()
    const next = forward
      ? stops.find((stop) => stop > y + 2)
      : [...stops].reverse().find((stop) => stop < y - 2)
    if (next === undefined) return
    event.preventDefault()
    glideTo(next)
  }
  window.addEventListener("keydown", onKey)
  window.addEventListener("keydown", onOtherInput, { capture: true })
  window.addEventListener("pointerdown", onOtherInput, { capture: true })

  let frame = 0
  const raf = (time: number) => {
    lenis.raf(time)
    frame = requestAnimationFrame(raf)
  }
  frame = requestAnimationFrame(raf)

  return () => {
    cancelAnimationFrame(frame)
    window.clearTimeout(gestureEnd)
    window.removeEventListener("keydown", onKey)
    window.removeEventListener("keydown", onOtherInput, { capture: true })
    window.removeEventListener("pointerdown", onOtherInput, { capture: true })
    registerScroller(null)
    lenis.destroy()
  }
}
