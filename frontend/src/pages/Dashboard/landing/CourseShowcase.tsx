import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { motion, useReducedMotion, useScroll, useTransform } from "motion/react"

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

  // How far the row must move for its last card to reach the right edge.
  useEffect(() => {
    const row = rowRef.current
    if (!row || prefersReducedMotion) return

    const measure = () => setTravel(Math.max(0, row.scrollWidth - window.innerWidth + 48))
    measure()

    const observer = new ResizeObserver(measure)
    observer.observe(row)
    window.addEventListener("resize", measure)
    return () => {
      observer.disconnect()
      window.removeEventListener("resize", measure)
    }
  }, [courses, prefersReducedMotion])

  const { scrollYProgress } = useScroll({
    target: trackRef,
    offset: ["start start", "end end"],
  })
  const x = useTransform(scrollYProgress, [0, 1], [0, -travel])

  if (courses.length === 0) return null

  const heading = (
    <h2 className="font-serif text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
      {t("header.courses")}
    </h2>
  )

  if (prefersReducedMotion) {
    return (
      <section className="mx-auto w-full max-w-5xl px-4 py-24 sm:px-6">
        {heading}
        <ul className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {courses.map((course) => (
            <li key={course.id}>
              <CourseCard course={course} />
            </li>
          ))}
        </ul>
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
        <motion.ul ref={rowRef} style={{ x }} className="mt-10 flex w-max gap-6 px-4 sm:px-6">
          {courses.map((course) => (
            <li key={course.id} className="w-[300px] shrink-0 sm:w-[420px]">
              <CourseCard course={course} />
            </li>
          ))}
        </motion.ul>
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
