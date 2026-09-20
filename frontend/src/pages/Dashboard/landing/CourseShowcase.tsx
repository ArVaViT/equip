import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { useReducedMotion } from "motion/react"

import { coursesService } from "@/services/courses"
import { toProxyImage } from "@/lib/images"
import type { Course } from "@/types"

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
 * HOW THE DISTANCE IS DECIDED. The track is as tall as the row is wide.
 * Travel and scroll are then the same number of pixels, so the row moves at
 * the speed of the wheel — neither dragging behind nor racing ahead, which
 * is what makes a pinned horizontal section feel broken when the ratio is
 * picked by eye instead of measured. It is measured again on resize and
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
  const [travel, setTravel] = useState(0)

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
      setTravel(travelRef.current)
    }

    // Written straight from the scroll handler, with no easing pass in
    // between.
    //
    // The first version smoothed the value inside `requestAnimationFrame`,
    // which is correct on paper and has one fatal property: rAF does not run
    // in a background tab, so the row sat at its starting offset and the
    // transform never changed. Scroll is already smooth; interpolating it
    // adds lag and one more thing to be wrong. The shelf now moves exactly
    // as far as the page did, which is what was asked for — «чтоб они при
    // скроле двигались горизонтально».
    const apply = () => {
      const distance = travelRef.current
      if (distance <= 0) {
        row.style.transform = "translate3d(0, 0, 0)"
        return
      }
      // 0 when the track's top meets the top of the window, 1 when the page
      // has scrolled through exactly `distance`.
      const progress = Math.min(1, Math.max(0, -track.getBoundingClientRect().top / distance))
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

  const heading = (
    <h2 className="font-serif text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
      {t("header.courses")}
    </h2>
  )

  // Phones, tablets, and anybody who asked for less movement: a plain strip
  // they can swipe, or a grid if even that is too much.
  if (prefersReducedMotion || !pinned) {
    return (
      <section className="mx-auto w-full max-w-5xl px-5 py-20 sm:px-6 sm:py-24">
        {heading}
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
      </section>
    )
  }

  return (
    <div ref={trackRef} className="relative" style={{ height: `calc(100svh + ${travel}px)` }}>
      <div className="sticky top-0 flex h-[100svh] flex-col justify-center overflow-hidden">
        <div className="mx-auto w-full max-w-5xl px-4 sm:px-6">{heading}</div>

        {/* The row starts at the page's own left margin and runs off the
            right edge — a shelf that continues past the window, rather than
            a set of cards arranged to fit inside it. */}
        <ul ref={rowRef} className="mt-10 flex w-max gap-6 px-4 will-change-transform sm:px-6">
          {courses.map((course) => (
            <li key={course.id} className="w-[300px] shrink-0 sm:w-[420px]">
              <CourseCard course={course} />
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

function CourseCard({ course }: { course: Course }) {
  const cover = toProxyImage(course.image_url)

  return (
    <Link
      to={`/courses/${course.id}`}
      // The lift on hover is the only pointer-driven motion on the page,
      // which is why it is on the one element a visitor is meant to click.
      className="group flex h-full flex-col overflow-hidden rounded-xl border border-line bg-surface transition-transform duration-base ease-out hover:-translate-y-1"
    >
      <div className="aspect-[16/10] overflow-hidden bg-surface-muted">
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
      <div className="flex flex-1 flex-col p-5">
        <h3 className="font-serif text-lg font-semibold leading-snug text-ink">{course.title}</h3>
        {course.description ? (
          <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-ink-muted">
            {course.description}
          </p>
        ) : null}
      </div>
    </Link>
  )
}
