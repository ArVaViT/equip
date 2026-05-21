import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { motion, useReducedMotion } from "motion/react"
import { BookOpen, Sparkles } from "lucide-react"
import { toProxyImage } from "@/lib/images"
import type { Course } from "@/types"

interface Props {
  /** The course the user just enrolled in. We use its title + cover
   *  as the focal point of the splash; nothing else from the course
   *  is needed at this point. */
  course: Course
  /** Optional first name for the user — when present we add a
   *  light personal touch ("Welcome, Vadym"). Falsy values render
   *  the un-personalised variant. */
  firstName?: string | null
  /** Fires after the splash's visible window (~1.2s) elapses. The
   *  caller uses it to ``navigate`` to the course detail page. */
  onComplete: () => void
}

const EDITORIAL_EASE: [number, number, number, number] = [0.22, 1, 0.36, 1]
const VISIBLE_MS = 1200
const VISIBLE_MS_REDUCED = 400

/**
 * 1.2-second typographic celebration shown right after the first-
 * run picker enrolls the user. Turns ``click → navigate`` into a
 * remembered moment: the course cover + serif title fade up on the
 * paper background with a calm sage rule above, the page stays
 * frozen for a beat, then ``onComplete`` fires and the caller
 * navigates to ``/courses/{id}``.
 *
 * On ``prefers-reduced-motion`` the splash stays but the visible
 * window collapses to 400 ms and the fade animations turn off —
 * the celebration is still there, just immediate. We don't skip
 * it entirely; the reflex of saving the moment matters more than
 * the animation itself.
 */
export function EnrollSplash({ course, firstName, onComplete }: Props) {
  const { t } = useTranslation()
  const prefersReducedMotion = useReducedMotion()
  const cover = course.image_url ? toProxyImage(course.image_url) : null
  const visibleMs = prefersReducedMotion ? VISIBLE_MS_REDUCED : VISIBLE_MS

  useEffect(() => {
    const id = window.setTimeout(onComplete, visibleMs)
    return () => window.clearTimeout(id)
  }, [onComplete, visibleMs])

  // ``key`` on the motion children isn't needed since the splash
  // mounts once per render. We rely on Framer Motion's entry
  // animations to play on mount and let the parent unmount us
  // when ``onComplete`` triggers the navigation.
  return (
    <div
      role="status"
      aria-live="polite"
      // Same stacking layer as the FirstRunFlow modal — the picker
      // unmounts a moment before this mounts, so there's no
      // overlap, but using the same z-index keeps the splash above
      // any latent driver.js overlay just in case.
      className="fixed inset-0 z-[2147483646] flex flex-col items-center justify-center gap-6 overflow-hidden bg-background px-6 text-center"
    >
      <motion.span
        className="block h-px w-12 bg-accent/70"
        initial={prefersReducedMotion ? false : { opacity: 0, scaleX: 0 }}
        animate={{ opacity: 1, scaleX: 1 }}
        transition={{ duration: 0.5, ease: EDITORIAL_EASE }}
        aria-hidden
      />
      <motion.p
        className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.22em] text-accent"
        initial={prefersReducedMotion ? false : { opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, delay: 0.1, ease: EDITORIAL_EASE }}
      >
        <Sparkles className="h-3 w-3" strokeWidth={1.75} aria-hidden />
        {firstName
          ? t("firstRun.splash.eyebrowNamed", { name: firstName })
          : t("firstRun.splash.eyebrow")}
      </motion.p>
      <motion.div
        initial={prefersReducedMotion ? false : { opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.6, delay: 0.18, ease: EDITORIAL_EASE }}
        className="flex flex-col items-center gap-5"
      >
        {cover ? (
          <img
            src={cover}
            alt=""
            className="h-28 w-28 rounded-md border border-border object-cover shadow-[0_18px_45px_hsl(var(--foreground)/0.18)] sm:h-32 sm:w-32"
          />
        ) : (
          <div className="flex h-28 w-28 items-center justify-center rounded-md border border-border bg-muted text-muted-foreground shadow-[0_18px_45px_hsl(var(--foreground)/0.12)] sm:h-32 sm:w-32">
            <BookOpen className="h-10 w-10" strokeWidth={1.5} aria-hidden />
          </div>
        )}
        <h1 className="max-w-2xl text-balance font-serif text-3xl font-semibold leading-tight tracking-tight text-foreground sm:text-4xl">
          {course.title}
        </h1>
      </motion.div>
      <motion.p
        className="max-w-md text-sm leading-relaxed text-muted-foreground sm:text-base"
        initial={prefersReducedMotion ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.55, delay: 0.45, ease: EDITORIAL_EASE }}
      >
        {t("firstRun.splash.body")}
      </motion.p>
    </div>
  )
}
