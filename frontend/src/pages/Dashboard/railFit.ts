import { useLayoutEffect, type RefObject } from "react"

/**
 * The dashboard's right rail — verse, calendar, question — shares the
 * column exactly: «не меньше не больше». A long verse gets a tall verse
 * card, a long question a tall question card, and what the three do not
 * need is shared out evenly, so no card ends in an empty tail and nothing
 * is left under the last one.
 *
 * Short of room, the cards give way in order: the calendar first (down to
 * `MIN_CALENDAR`, scrolling inside), then the question (down to
 * `MIN_QUESTION`), the verse last. CSS grid cannot express that order: it
 * shares a shortfall between the rows that may shrink, and on a 720px
 * window it squeezed the calendar to its header while the question kept
 * all of its height.
 *
 * Desktop only (the rail is a column of ordinary cards below `lg`), and
 * the rows are written as pixel heights on the rail's grid. The cards
 * centre their own content in the room they are given.
 */

const MIN_CALENDAR = 120
const MIN_QUESTION = 160
const MIN_VERSE = 96

/** Height a card needs: its box, less its body's box, plus its body's content. */
function naturalHeight(wrapper: HTMLElement): number {
  const card = wrapper.firstElementChild as HTMLElement | null
  if (!card) return 0
  const body = card.lastElementChild as HTMLElement | null
  if (!body || body === card.firstElementChild) return card.offsetHeight
  const style = getComputedStyle(body)
  const gap = parseFloat(style.rowGap) || 0
  const children = [...body.children] as HTMLElement[]
  const content =
    children.reduce((sum, child) => sum + child.offsetHeight, 0) +
    gap * Math.max(0, children.length - 1) +
    (parseFloat(style.paddingTop) || 0) +
    (parseFloat(style.paddingBottom) || 0)
  return card.offsetHeight - body.clientHeight + content
}

/** Pure distribution, exported for tests. `[verse, calendar, question]`. */
export function distributeRail(natural: number[], available: number): number[] {
  const heights = [...natural]
  const present = heights.map((h) => h > 0)
  const total = heights.reduce((a, b) => a + b, 0)
  if (total <= available) {
    const count = present.filter(Boolean).length || 1
    const extra = (available - total) / count
    return heights.map((h, i) => (present[i] ? h + extra : 0))
  }
  let over = total - available
  const floors = [MIN_VERSE, MIN_CALENDAR, MIN_QUESTION]
  for (const i of [1, 2, 0]) {
    if (over <= 0) break
    const h = heights[i] ?? 0
    const floor = Math.min(h, floors[i] ?? 0)
    const cut = Math.min(over, h - floor)
    heights[i] = h - cut
    over -= cut
  }
  return heights
}

export function useRailFit(rail: RefObject<HTMLDivElement | null>, enabled: boolean): void {
  useLayoutEffect(() => {
    const el = rail.current
    if (!el || !enabled || typeof window.matchMedia !== "function") return
    const desktop = window.matchMedia("(min-width: 1024px)")
    let frame = 0

    const fit = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        if (!desktop.matches) {
          el.style.gridTemplateRows = ""
          return
        }
        const wrappers = [...el.children] as HTMLElement[]
        const gap = parseFloat(getComputedStyle(el).rowGap) || 0
        const natural = wrappers.map(naturalHeight)
        const shown = natural.filter((h) => h > 0).length
        const available = el.clientHeight - gap * Math.max(0, shown - 1)
        const heights = distributeRail(natural, available)
        el.style.gridTemplateRows = heights.map((h) => `${Math.max(0, Math.floor(h))}px`).join(" ")
      })
    }

    fit()
    // The rail's own size (window, banners) and its content (a card
    // loading, an answer revealing the explanation) both move the answer.
    const resize = new ResizeObserver(fit)
    resize.observe(el)
    const mutation = new MutationObserver(fit)
    mutation.observe(el, { childList: true, subtree: true, characterData: true })
    desktop.addEventListener("change", fit)
    return () => {
      cancelAnimationFrame(frame)
      resize.disconnect()
      mutation.disconnect()
      desktop.removeEventListener("change", fit)
      el.style.gridTemplateRows = ""
    }
  }, [rail, enabled])
}
