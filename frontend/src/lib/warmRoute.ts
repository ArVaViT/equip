import { hasStoredSupabaseSession } from "@/lib/storedSession"
import { isPhone } from "@/pages/Dashboard/landing/phoneCut"
import { TOUR } from "@/pages/Dashboard/landing/tourCuts"

/**
 * Start fetching what the first page needs while the app is still booting.
 *
 * Without this, a cold load on a phone was a strict queue: the entry chunk,
 * then the locale catalog (`i18nReady` gates the first render), then the
 * first render, then the route's lazy chunk, then that chunk's own lazy
 * pieces, and only then the LCP image. Every step waited for the one before
 * it, and each one is a round trip on a mobile connection. Lighthouse
 * (mobile, 2026-10-15) put the landing's LCP at 5.6 s and the course page's
 * at 4.7 s, nearly all of it this queue rather than bytes.
 *
 * The chunk imports here are the very ones `App.tsx` makes lazily — same
 * module specifiers, so the browser fetches each file once and the router
 * finds it already loaded. Only the public entry pages are listed: they are
 * where a first visit lands, and where LCP is measured. Anything else boots
 * as before.
 *
 * Every failure is swallowed: this is a head start, never a dependency. The
 * route's own lazy load still runs, and still recovers from a stale deploy
 * (`lazyRoute`).
 */
const COURSE = /^\/courses\/[^/]+\/?$/
const CHAPTER = /^\/courses\/[^/]+\/(?:modules\/[^/]+\/)?chapters\/[^/]+\/?$/

export function warmRoute(pathname: string): void {
  const ignore = () => undefined
  if (pathname === "/") {
    void import("@/pages/Dashboard/DashboardPage").catch(ignore)
    // A stored session means the dashboard, not the landing (see the same
    // check in App.tsx's DashboardPage loader).
    if (hasStoredSupabaseSession()) return
    void import("@/pages/Dashboard/PublicLanding").catch(ignore)
    // Phone only: that is where the poster is the largest paint (on a wide
    // screen it is the headline, and the 150 kB landscape still would only
    // compete with the scripts that draw it).
    if (isPhone()) preloadImage(TOUR.phone.poster)
  } else if (pathname === "/courses" || pathname === "/courses/") {
    void import("@/pages/Courses/CoursesPage").catch(ignore)
  } else if (COURSE.test(pathname)) {
    void import("@/pages/Course/CourseDetail").catch(ignore)
  } else if (CHAPTER.test(pathname)) {
    void import("@/pages/Course/ChapterView").catch(ignore)
  }
}

/**
 * The tour's poster is the landing's largest paint on a phone, and as a
 * `<video poster>` it is invisible to the preload scanner until React has
 * rendered the page. Asking for it now, at high priority, takes it off the
 * end of the queue.
 */
function preloadImage(href: string): void {
  const link = document.createElement("link")
  link.rel = "preload"
  link.setAttribute("as", "image")
  link.href = href
  link.setAttribute("fetchpriority", "high")
  document.head.appendChild(link)
}
