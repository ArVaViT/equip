import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  AnimatePresence,
  motion,
  useMotionValueEvent,
  useReducedMotion,
  useScroll,
  useTransform,
} from "motion/react"

import { EDITORIAL_EASE, MOTION_DURATION } from "@/lib/motion"

import { scrollPageTo } from "./scrollControl"

/**
 * Three claims told over one scene that never stops moving.
 *
 * The page below the hero used to be three paragraphs in a column, each
 * fading in once. Next to a hero that moves, prose that sits still reads as
 * the page giving up — «а дальше слабенько», and fairly.
 *
 * The scene itself now lives in `LandingBackdrop`, fixed behind the whole
 * page, so this section holds only the words. It still holds them for three
 * screens of scrolling, against the stretch of the backdrop where the
 * leaves stack, fan and come forward — the claims are captions to that
 * movement, which is why their timings are tuned to it.
 *
 * THE TRACK. The sticky child is one viewport tall; each claim then owns
 * `STEP_SVH` of scrolling. The numbers, and why the old 300svh was too
 * short, are with the constant.
 * `svh` rather than `vh` because mobile browser chrome changes `vh`
 * mid-scroll, which would shift every caption boundary as the toolbar hides.
 *
 * Under `prefers-reduced-motion` none of this exists: no canvas, no sticky
 * track, no scroll listener — the three claims render as an ordinary column,
 * which is what a screen reader and a crawler see in every case.
 */


export function StorySection() {
  const { t } = useTranslation()
  const prefersReducedMotion = useReducedMotion()

  // The sticky track exists to hold the reader still while the backdrop
  // moves behind them. Until 2026-09-23 there was no backdrop below `lg`,
  // so the track stopped there too — three screens of scrolling with one
  // short sentence floating in each would have been empty. The scene now
  // runs on phones as well, so the stage goes wherever the scene goes: any
  // real browser (`matchMedia` is the check; jsdom and a few old engines
  // lack it and get the column) that has not asked for less motion.
  const [pinned, setPinned] = useState(false)
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return
    setPinned(true)
  }, [])

  // Literal keys, one call per string — a template key would be invisible to
  // the ``keyCoverage`` check (docs/I18N.md).
  const claims = [
    {
      title: t("landing.value.structure.title"),
      body: t("landing.value.structure.body"),
    },
    {
      title: t("landing.value.assessment.title"),
      body: t("landing.value.assessment.body"),
    },
    {
      title: t("landing.value.certificates.title"),
      body: t("landing.value.certificates.body"),
    },
  ]

  if (prefersReducedMotion || !pinned) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-14 px-5 py-20 sm:gap-16">
        {claims.map((claim) => (
          <Claim key={claim.title} title={claim.title} body={claim.body} />
        ))}
      </div>
    )
  }

  return <PinnedClaims claims={claims} />
}

/**
 * Scroll distance given to each claim, in `svh`.
 *
 * It was 300svh for the whole track, with the hand-over at a third and two
 * thirds of the 200svh that actually scrolls — one claim every ~67svh, about
 * 600px, which a single flick of a trackpad covers. «От A course, not a pile
 * of videos до A certificate you can verify очень быстрая прокрутка»: the
 * second claim was on screen for less time than it takes to read it.
 *
 * Now each claim owns 110svh, and there is a rest stop at each one (see
 * `STOPS` below), so the reader arrives on a claim and stays there until
 * they choose to move on.
 */
const STEP_SVH = 110

/** The backdrop's pose behind each claim, in order — see `LandingBackdrop`. */
const CLAIM_POSES = ["stacked", "fanned", "single"] as const

/*
 * No tail after the last claim. There was one (50svh) to hold the third
 * claim before the track let go; the wall in `pageScroll.ts` now does that
 * holding, and the tail had become a stretch with no scene in it — a flick
 * off the third claim came to rest there, between the claims and the tour,
 * looking at nothing.
 */

/**
 * The sticky version, and the only place `useScroll` is called.
 *
 * It lives in its own component because `useScroll({ target })` must never
 * be called while the element it points at is unrendered. A hook cannot be
 * called conditionally, so when the track and the hook sat in one component
 * the hook still ran on a phone — where the plain column renders and the
 * ref is never attached — and motion threw `Target ref is defined but not
 * hydrated` from a microtask after the effects flushed. In production that
 * invariant compiles away, so nobody saw it; in development and in CI it is
 * an uncaught exception, and it turned the whole frontend suite red with
 * 1,471 tests passing and no test failing.
 *
 * Mounting the hook together with its target removes the case rather than
 * guarding against it.
 */
function PinnedClaims({ claims }: { claims: { title: string; body: string }[] }) {
  const { t } = useTranslation()
  const trackRef = useRef<HTMLDivElement>(null)
  const stopRefs = useRef<(HTMLDivElement | null)[]>([])
  const { scrollYProgress } = useScroll({
    target: trackRef,
    offset: ["start start", "end end"],
  })

  const last = claims.length - 1
  const trackSvh = 100 + STEP_SVH * last
  // Where each stop sits on the 0..1 progress of the track. Claim `k` is
  // shown from halfway before its stop to halfway after it.
  const stopAt = (k: number) => (STEP_SVH * k) / (trackSvh - 100)

  // One caption exists at a time.
  //
  // Three of them used to sit in the same grid cell, cross-fading by
  // opacity. On paper the ranges never overlap; on a real wheel they do —
  // a fast scroll jumps the progress value straight past the handover, and
  // for those frames two full paragraphs are painted on top of each other.
  // Vadym saw exactly that: «он стал перекрывать друг друга».
  //
  // So the index is state, and only the active caption is mounted.
  // Overlapping text is then not a thing that can happen, at any scroll
  // speed, rather than a thing the numbers say should not.
  const [active, setActive] = useState(0)
  // Which way the reader is going, so a caption leaves in the direction the
  // page is moving instead of always upward.
  const [direction, setDirection] = useState(1)
  useMotionValueEvent(scrollYProgress, "change", (value) => {
    let next = 0
    for (let k = 1; k <= last; k++) {
      if (value >= (stopAt(k - 1) + stopAt(k)) / 2) next = k
    }
    setActive((current) => {
      if (current !== next) setDirection(next > current ? 1 : -1)
      return next
    })
  })

  // The rail's fill runs from the first stop to the last, not across the
  // tail, so it reads "complete" exactly when the third claim arrives.
  const fill = useTransform(scrollYProgress, [0, stopAt(last)], [0, 1], { clamp: true })

  const goTo = (k: number) => {
    const stop = stopRefs.current[k]
    if (!stop) return
    scrollPageTo(stop.getBoundingClientRect().top + window.scrollY)
  }

  return (
    <div ref={trackRef} className="relative" style={{ height: `${trackSvh}svh` }}>
      {/* STOPS. One invisible marker per claim, at the scroll offset where
          that claim is centred in its own stretch. Each is a rest stop for
          the page's wheel handling (`pageScroll.ts`) and a pose anchor for
          the backdrop, so a reader who stops scrolling comes to rest on a
          claim with the scene fully formed behind it, not halfway between
          two. */}
      {claims.map((claim, k) => (
        <div
          key={claim.title}
          ref={(el) => {
            stopRefs.current[k] = el
          }}
          data-backdrop-pose={CLAIM_POSES[k] ?? "stacked"}
          data-scene-stop="start"
          aria-hidden
          className="pointer-events-none absolute inset-x-0 h-px"
          style={{ top: `${STEP_SVH * k}svh` }}
        />
      ))}

      <div className="sticky top-0 isolate flex h-[100svh] items-center overflow-hidden">
        <div className="relative z-10 mx-auto w-full max-w-5xl px-4">
          <AnimatePresence initial={false} custom={direction}>
            <motion.div
              key={active}
              custom={direction}
              variants={{
                enter: (dir: number) => ({ opacity: 0, y: 28 * dir }),
                shown: { opacity: 1, y: 0 },
                leave: (dir: number) => ({ opacity: 0, y: -28 * dir, position: "absolute" }),
              }}
              initial="enter"
              animate="shown"
              exit="leave"
              transition={{ duration: MOTION_DURATION.panel, ease: EDITORIAL_EASE }}
            >
              <Claim title={claims[active]?.title ?? ""} body={claims[active]?.body ?? ""} />
            </motion.div>
          </AnimatePresence>
        </div>

        {/* The rail. Where the reader is inside the section, and how much is
            left — the thing a pinned section otherwise hides, because the
            scrollbar stops meaning anything while the page is held. Claude's
            product page does the same with a clock running 8AM → 4PM down
            the side of its pinned band. Each mark is a button to its stop. */}
        <nav
          aria-label={t("landing.value.heading")}
          // On a phone the rail lies down: a row of numbers under the
          // caption, where a thumb is, instead of a column in a 16px margin.
          className="absolute bottom-10 left-1/2 z-10 flex -translate-x-1/2 items-stretch gap-3 lg:bottom-auto lg:left-auto lg:right-6 lg:top-1/2 lg:-translate-y-1/2 lg:translate-x-0 xl:right-10"
        >
          <div className="relative hidden w-px bg-line lg:block">
            <motion.div
              className="absolute inset-x-0 top-0 h-full origin-top bg-ink"
              style={{ scaleY: fill }}
            />
          </div>
          <ol className="flex flex-row gap-6 lg:flex-col lg:gap-7">
            {claims.map((claim, k) => (
              <li key={claim.title}>
                <button
                  type="button"
                  onClick={() => goTo(k)}
                  aria-current={k === active ? "step" : undefined}
                  aria-label={claim.title}
                  className={
                    "font-mono text-xs tabular-nums tracking-wider transition-colors duration-base ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand " +
                    (k === active ? "font-semibold text-ink" : "text-ink-muted hover:text-ink")
                  }
                >
                  {String(k + 1).padStart(2, "0")}
                </button>
              </li>
            ))}
          </ol>
        </nav>
      </div>
    </div>
  )
}

function Claim({ title, body }: { title: string; body: string }) {
  return (
    <div className="max-w-2xl">
      <h3 className="font-serif text-3xl font-medium leading-tight tracking-[-0.025em] text-ink sm:text-5xl">
        {title}
      </h3>
      <p className="mt-4 max-w-xl text-base leading-relaxed text-ink-muted sm:text-lg">{body}</p>
    </div>
  )
}
