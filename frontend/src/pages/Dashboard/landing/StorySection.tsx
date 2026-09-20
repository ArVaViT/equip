import { lazy, Suspense, useRef, useState } from "react"
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
 * Now the canvas is held (`sticky`) for three screens of scrolling while the
 * leaves pass from stack to row to single sheet, and each claim is on screen
 * for exactly the stretch where the scene is making its point. The words are
 * captions; the scene is the argument.
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

const StoryScene = lazy(() => import("./StoryScene"))

export function StorySection() {
  const { t } = useTranslation()
  const prefersReducedMotion = useReducedMotion()
  const trackRef = useRef<HTMLDivElement>(null)

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

  if (prefersReducedMotion) {
    return (
      <div className="flex flex-col gap-16">
        {claims.map((claim) => (
          <Claim key={claim.title} title={claim.title} body={claim.body} />
        ))}
      </div>
    )
  }

  return (
    <div ref={trackRef} className="relative h-[300svh]">
      <div className="sticky top-0 isolate flex h-[100svh] items-center overflow-hidden">
        <Suspense fallback={null}>
          <StoryScene
            // Same fade top and bottom as the hero: the sticky frame has a
            // hard edge at both ends, and a leaf crossing either one was
            // being cut flat.
            className="pointer-events-none absolute inset-0 z-0 [mask-image:linear-gradient(to_bottom,transparent_0%,black_18%,black_82%,transparent_100%)]"
          />
        </Suspense>

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
