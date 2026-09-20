import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { motion, useReducedMotion } from "motion/react"

import { coursesService } from "@/services/courses"
import { toProxyImage } from "@/lib/images"
import { EDITORIAL_EASE, MOTION_DURATION } from "@/lib/motion"
import type { Course } from "@/types"

/**
 * The courses themselves, on the page that is trying to sell them.
 *
 * Everything above this argues about *how* the platform teaches. None of it
 * said what is actually on it — the catalogue sat behind a button, and the
 * covers, which are the best-looking thing Equip owns, were never seen by
 * anybody who had not already clicked through.
 *
 * Live from `GET /courses`, the same public endpoint the catalogue uses, so
 * this cannot drift into advertising a course that was unpublished last
 * month. Three of them: enough to show there is a shelf, few enough to stay
 * a glance rather than a list.
 *
 * WHEN IT RENDERS NOTHING: while loading, if the request fails, or if the
 * catalogue is empty. Same rule as the intro film — a section that promises
 * courses and then shows three grey rectangles is worse than no section, and
 * a landing page that breaks because an API call failed is worse than both.
 */

const SHOWN = 3

export function CourseShowcase() {
  const { t } = useTranslation()
  const prefersReducedMotion = useReducedMotion()
  const [courses, setCourses] = useState<Course[]>([])

  useEffect(() => {
    let alive = true
    coursesService
      .getCourses(undefined, { limit: SHOWN })
      .then((list: Course[]) => {
        if (alive) setCourses(list.slice(0, SHOWN))
      })
      .catch(() => {
        // Deliberately silent. The catalogue being unreachable is not
        // something to tell a first-time visitor about on the marketing
        // page; the section simply is not there.
      })
    return () => {
      alive = false
    }
  }, [])

  if (courses.length === 0) return null

  return (
    <section className="mx-auto w-full max-w-5xl px-4 py-24 sm:px-6 sm:py-32">
      {/* `header.courses` («Курсы»), not `dashboard.browseAllCta` («Открыть
          каталог»): the first is a name for a section, the second is what a
          button says. Both already exist in all four locales, so neither
          adds a key to translate. */}
      <h2 className="font-serif text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
        {t("header.courses")}
      </h2>

      <ul className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {courses.map((course, i) => {
          const cover = toProxyImage(course.image_url)
          const card = (
            <Link
              to={`/courses/${course.id}`}
              // The lift on hover is the only interactive motion on the page
              // that responds to a pointer rather than to scroll — which is
              // exactly why it belongs on the one element here a visitor is
              // meant to click.
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
                <h3 className="font-serif text-lg font-semibold leading-snug text-ink">
                  {course.title}
                </h3>
                {course.description ? (
                  <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-ink-muted">
                    {course.description}
                  </p>
                ) : null}
              </div>
            </Link>
          )

          return (
            <li key={course.id} className="h-full">
              {prefersReducedMotion ? (
                card
              ) : (
                <motion.div
                  className="h-full"
                  initial={{ opacity: 0, y: 16 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: "0px 0px -10% 0px" }}
                  transition={{
                    duration: MOTION_DURATION.panel,
                    ease: EDITORIAL_EASE,
                    delay: i * 0.08,
                  }}
                >
                  {card}
                </motion.div>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
