import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { AnimatePresence, motion, useMotionValueEvent, useReducedMotion, useScroll } from "motion/react"

import { EDITORIAL_EASE, MOTION_DURATION } from "@/lib/motion"

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
 * WHY THE TRACK IS 300svh. The sticky child is one viewport tall, so the
 * scrollable remainder — 200svh — is the distance over which the three
 * states play. Less and the transitions trip over each other; more and the
 * reader is scrolling through a section that has stopped saying anything.
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
  const trackRef = useRef<HTMLDivElement>(null)

  // The sticky track exists to hold the reader still while the backdrop
  // moves behind them. Below `lg` there is no backdrop — it is a desktop
  // luxury that reads as grey shapes across the headline on a phone — so
  // the track was three screens of scrolling with one short sentence
  // floating in the middle of each empty one. Same breakpoint as the
  // backdrop on purpose: when the scene goes, its stage goes with it.
  const [pinned, setPinned] = useState(false)
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return
    const query = window.matchMedia("(min-width: 1024px)")
    const sync = () => setPinned(query.matches)
    sync()
    query.addEventListener("change", sync)
    return () => query.removeEventListener("change", sync)
  }, [])

  const { scrollYProgress } = useScroll({
    target: trackRef,
    offset: ["start start", "end end"],
  })

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
  useMotionValueEvent(scrollYProgress, "change", (value) => {
    const next = value < 0.34 ? 0 : value < 0.67 ? 1 : 2
    setActive((current) => (current === next ? current : next))
  })

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

  return (
    <div ref={trackRef} className="relative h-[300svh]">
      <div className="sticky top-0 isolate flex h-[100svh] items-center overflow-hidden">
        {/* `mode="wait"` would leave a gap with no caption at all; the
            default lets the outgoing one fade while the incoming arrives,
            and since only one is ever mounted they cannot collide. */}
        <div className="relative z-10 mx-auto w-full max-w-5xl px-4">
          <AnimatePresence initial={false}>
            <motion.div
              key={active}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, position: "absolute" }}
              transition={{ duration: MOTION_DURATION.panel, ease: EDITORIAL_EASE }}
            >
              <Claim title={claims[active]?.title ?? ""} body={claims[active]?.body ?? ""} />
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}

function Claim({ title, body }: { title: string; body: string }) {
  return (
    <div className="max-w-2xl">
      <h3 className="font-serif text-3xl font-semibold leading-tight tracking-tight text-ink sm:text-5xl">
        {title}
      </h3>
      <p className="mt-4 max-w-xl text-base leading-relaxed text-ink-muted sm:text-lg">{body}</p>
    </div>
  )
}
