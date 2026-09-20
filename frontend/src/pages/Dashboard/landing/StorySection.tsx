import { lazy, Suspense, useRef } from "react"
import { useTranslation } from "react-i18next"
import { motion, useReducedMotion, useScroll, useTransform } from "motion/react"

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

  // Each caption holds, then hands over. The gaps are where the scene is
  // mid-transition and a fixed sentence would be describing the wrong shape.
  // The first caption starts *visible*. It used to fade up from zero over
  // the opening 6% of the track, which meant the reader arrived at the
  // section and found a moving scene with no words against it — the caption
  // only appeared once they had already scrolled past the question it was
  // answering.
  const first = useTransform(scrollYProgress, [0, 0.27, 0.34], [1, 1, 0])
  const second = useTransform(scrollYProgress, [0.34, 0.41, 0.6, 0.67], [0, 1, 1, 0])
  const third = useTransform(scrollYProgress, [0.67, 0.74, 0.95, 1], [0, 1, 1, 1])

  // Literal keys, one call per string — a template key would be invisible to
  // the ``keyCoverage`` check (docs/I18N.md).
  const claims = [
    {
      title: t("landing.value.structure.title"),
      body: t("landing.value.structure.body"),
      opacity: first,
    },
    {
      title: t("landing.value.assessment.title"),
      body: t("landing.value.assessment.body"),
      opacity: second,
    },
    {
      title: t("landing.value.certificates.title"),
      body: t("landing.value.certificates.body"),
      opacity: third,
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

        {/* The captions share one grid cell, so they cross-fade in place
            instead of the block changing height under the reader. */}
        <div className="relative z-10 mx-auto grid w-full max-w-5xl px-4">
          {claims.map((claim) => (
            <motion.div
              key={claim.title}
              style={{ opacity: claim.opacity, gridArea: "1 / 1" }}
              className="flex items-center"
            >
              <Claim title={claim.title} body={claim.body} />
            </motion.div>
          ))}
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
