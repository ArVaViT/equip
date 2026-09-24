import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { useReducedMotion } from "motion/react"

import { coursesService } from "@/services/courses"
import { toProxyImage } from "@/lib/images"
import type { Course } from "@/types"

import { SceneBand } from "./SceneBand"

/**
 * The whole shelf, travelling sideways while the page goes down.
 *
 * Three cards in a grid was a sample; this is the catalogue. Scrolling down
 * moves the row across, which buys two things a grid does not: every course
 * is shown without asking for three screens of height, and the row keeps
 * moving with the reader instead of waiting for them — the same argument as
 * the scene above it.
 *
 * CARD WIDTH IS PART OF THE MECHANISM. At 340px the five courses came to
 * 1844px, which fits inside a 1920px window — so the row had nowhere to
 * travel and the section quietly did nothing on exactly the screens most
 * likely to see it. At 420px the shelf runs past the edge of any desktop,
 * which is both the effect and the honest picture: a catalogue that
 * continues past the window.
 *
 * WHY NOT `useScroll` + `useTransform`. That was the first version and the
 * row never moved: `travel` is 0 on the first render, so the transform was
 * built over the range [0, -0], and a value that is always zero never
 * reaches the DOM — `getComputedStyle(row).transform` stayed `"none"` at
 * every scroll position. Re-rendering with the measured width did not
 * rebuild it. The scroll handler below reads the distance from a ref, so it
 * is never stale, and writes the transform itself, so there is nothing
 * between the measurement and the pixels.
 *
 * HOW FAR AND HOW FAST. The row's overhang — how much wider it is than the
 * window — is measured, and spread across the section's whole journey
 * through the viewport. So the last card arrives at the right edge exactly
 * as the section leaves the top, and the speed follows from the geometry
 * rather than from a ratio picked by eye. Re-measured on resize and
 * whenever the catalogue changes, because it depends on both.
 *
 * It renders nothing while loading, nothing if the request fails, and
 * nothing if the catalogue is empty — the same rule the film follows. Under
 * `prefers-reduced-motion` it is an ordinary wrapping grid: no pinning, no
 * sideways movement, no scroll listener.
 */

export function CourseShowcase() {
  const { t } = useTranslation()
  const prefersReducedMotion = useReducedMotion()
  // A pinned shelf is a desktop idea. On a phone it turned five courses
  // into two and a half screens of vertical scrolling, and it competes with
  // the gesture the reader already has: a thumb. Below `lg` the row is an
  // ordinary swipeable strip with snap points — faster to get through, and
  // the thing a phone user expects a row of cards to do.
  const [pinned, setPinned] = useState(false)
  useEffect(() => {
    // `matchMedia` is missing in jsdom and in a few old mobile engines.
    // Without this guard the whole landing page threw on render there —
    // nine tests went red at once, all of them about the hero, none of them
    // about this component. Falling back to the swipeable strip is also the
    // right default: it works with a thumb and with a wheel.
    if (typeof window.matchMedia !== "function") return

    const query = window.matchMedia("(min-width: 1024px)")
    const sync = () => setPinned(query.matches)
    sync()
    query.addEventListener("change", sync)
    return () => query.removeEventListener("change", sync)
  }, [])
  const [courses, setCourses] = useState<Course[]>([])
  const trackRef = useRef<HTMLDivElement>(null)
  const rowRef = useRef<HTMLUListElement>(null)

  useEffect(() => {
    let alive = true
    coursesService
      .getCourses()
      .then((list: Course[]) => {
        if (alive) setCourses(list)
      })
      .catch(() => {
        // Deliberately silent: a catalogue outage is not something to tell a
        // first-time visitor about on the marketing page.
      })
    return () => {
      alive = false
    }
  }, [])

  // How far the row must move for its last card to reach the right edge,
  // kept in a ref so the scroll handler always reads the current value.
  const travelRef = useRef(0)

  useEffect(() => {
    const row = rowRef.current
    const track = trackRef.current
    if (!row || !track || prefersReducedMotion || !pinned) return

    const measure = () => {
      travelRef.current = Math.max(0, row.scrollWidth - window.innerWidth + 48)
    }

    // The shelf moves *while* the page scrolls past it. It does not hold the
    // page still to do it.
    //
    // The first version pinned the section: a tall track, a `sticky` child,
    // and the row consuming 852px of vertical scroll before the page could
    // continue. That is a common pattern and it is the one thing Vadym did
    // not want — «не надо прерывать скрол». Taking over the wheel for a
    // second and a half is the web equivalent of talking over somebody.
    //
    // So progress is measured from the section's *journey through the
    // window*: 0 when its top edge enters at the bottom, 1 when its bottom
    // edge leaves at the top. Scrolling stays exactly as long as the
    // content, the row travels the whole time it is visible, and nothing is
    // captured.
    const apply = () => {
      const distance = travelRef.current
      if (distance <= 0) {
        row.style.transform = "translate3d(0, 0, 0)"
        return
      }
      const rect = track.getBoundingClientRect()
      const journey = window.innerHeight + rect.height
      const travelled = window.innerHeight - rect.top
      const progress = Math.min(1, Math.max(0, travelled / journey))
      row.style.transform = `translate3d(${-progress * distance}px, 0, 0)`
    }

    measure()
    apply()

    // Two independent paths to the same write, because each one fails in a
    // situation the other survives.
    //
    // `scroll` is exact and cheap, and it is all that is needed while the
    // tab is in front. A rAF loop, running only while the shelf is on
    // screen, covers everything that moves the page without firing a scroll
    // event at this element — anchor jumps, a restored scroll position, the
    // moment a lazy image above resizes the document under the reader. Both
    // call the same `apply`, which is idempotent.
    const observer = new ResizeObserver(() => {
      measure()
      apply()
    })
    observer.observe(row)
    window.addEventListener("scroll", apply, { passive: true })
    window.addEventListener("resize", measure)

    let frame = 0
    let watching = false
    const loop = () => {
      frame = requestAnimationFrame(loop)
      apply()
    }
    const visibility = new IntersectionObserver(([entry]) => {
      const onScreen = entry?.isIntersecting ?? false
      if (onScreen && !watching) {
        watching = true
        frame = requestAnimationFrame(loop)
      } else if (!onScreen && watching) {
        watching = false
        cancelAnimationFrame(frame)
      }
    })
    visibility.observe(track)

    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      visibility.disconnect()
      window.removeEventListener("scroll", apply)
      window.removeEventListener("resize", measure)
    }
  }, [courses, prefersReducedMotion, pinned])

  if (courses.length === 0) return null

  // No heading. «Убери слово Courses, просто карусель курсов и все» — and
  // he is right: five covers with their titles on them do not need a label
  // reading "Courses" any more than a shelf of books needs one reading
  // "Books". The page still has an accessible name for the region, which is
  // what the heading was carrying that the covers do not.

  // Phones, tablets, and anybody who asked for less movement: a plain strip
  // they can swipe, or a grid if even that is too much.
  if (prefersReducedMotion || !pinned) {
    return (
      <SceneBand label={t("header.courses")} tone="sunken">
      <div className="mx-auto w-full max-w-5xl px-5 sm:px-6">
        {prefersReducedMotion ? (
          <ul className="mt-10 grid gap-6 sm:grid-cols-2">
            {courses.map((course) => (
              <li key={course.id}>
                <CourseCard course={course} />
              </li>
            ))}
          </ul>
        ) : (
          // `-mx-5`/`px-5` lets the strip bleed to both screen edges while
          // the first card still lines up with the heading above it, so it
          // reads as a shelf continuing past the phone rather than a box
          // that happens to scroll.
          <ul className="-mx-5 mt-8 flex snap-x snap-mandatory gap-4 overflow-x-auto px-5 pb-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {courses.map((course) => (
              <li key={course.id} className="w-[78vw] max-w-[320px] shrink-0 snap-start">
                <CourseCard course={course} />
              </li>
            ))}
          </ul>
        )}
      </div>
      </SceneBand>
    )
  }

  return (
    <div ref={trackRef} className="relative">
      {/* Staged on the darker of the two bands, so the tour above it and
          the shelf still read as two scenes — see `SceneBand`. */}
      <SceneBand label={t("header.courses")} tone="sunken" className="overflow-hidden">
        {/* The row starts at the page's own left margin and runs off the
            right edge — a shelf that continues past the window, rather than
            a set of cards arranged to fit inside it. */}
        <ul ref={rowRef} className="flex w-max gap-8 px-4 will-change-transform sm:px-6 lg:gap-10">
          {courses.map((course) => (
            <li key={course.id} className="w-[300px] shrink-0 sm:w-[460px]">
              <CourseCard course={course} />
            </li>
          ))}
        </ul>
      </SceneBand>
    </div>
  )
}

/**
 * A cover and its title — not a card.
 *
 * It was a white box with a hairline border, an image on top, a title and
 * two clamped lines of description: the exact anatomy of a display ad, and
 * Vadym read it as one — «карточки курсов выглядят как гугл реклама». The
 * box is what did it. Nothing else on this page sits in a white rectangle,
 * so five of them in a row read as inserted content rather than as the
 * catalogue.
 *
 * Now the cover *is* the object: large, rounded, lifted off the band by a
 * soft shadow, with the title set beneath it on the band itself, the way a
 * shelf of books or a row of films is shown. The description is gone — the
 * cover and the title are enough to choose from, and the course page is one
 * click away. The covers are 16:10 artwork, several with their own lettering
 * burnt in, so the title goes under the image, never over it.
 */
function CourseCard({ course }: { course: Course }) {
  const cover = toProxyImage(course.image_url)

  return (
    <Link
      to={`/courses/${course.id}`}
      className="group block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-4"
    >
      <div className="aspect-[16/10] overflow-hidden rounded-2xl bg-surface shadow-[0_18px_40px_-18px_hsl(var(--ink)/0.35)] ring-1 ring-ink/5 transition-transform duration-panel ease-out group-hover:-translate-y-1.5">
        {cover ? (
          <img
            src={cover}
            alt=""
            loading="lazy"
            decoding="async"
            className="h-full w-full object-cover transition-transform duration-panel ease-out group-hover:scale-[1.03]"
          />
        ) : null}
      </div>
      <h3 className="mt-5 text-pretty font-serif text-xl font-semibold leading-snug text-ink transition-colors duration-base group-hover:text-ink-muted">
        {course.title}
      </h3>
    </Link>
  )
}
