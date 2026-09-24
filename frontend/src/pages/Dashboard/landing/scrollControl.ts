/**
 * The one way landing-page code moves the page on purpose.
 *
 * On desktop the page is driven by Lenis (`pageScroll.ts`), and a native
 * `window.scrollTo({ behavior: "smooth" })` issued underneath it is two
 * animations fighting over one number. So anything that wants to take the
 * reader somewhere — the claims rail, for one — asks here, and this hands
 * the request to Lenis when it is running and to the browser when it is not
 * (phones, reduced motion, the first frames before the lazy chunk arrives).
 *
 * Deliberately tiny and free of `lenis` imports, so that importing it does
 * not pull the library into the main bundle.
 */

type Scroller = { scrollTo: (y: number) => void }

let active: Scroller | null = null

export function registerScroller(scroller: Scroller | null): void {
  active = scroller
}

export function scrollPageTo(y: number): void {
  if (active) {
    active.scrollTo(y)
    return
  }
  window.scrollTo({ top: y, behavior: "smooth" })
}
