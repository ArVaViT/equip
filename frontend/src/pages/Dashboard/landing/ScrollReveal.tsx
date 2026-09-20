import { useRef, type ReactNode } from "react"
import { motion, useReducedMotion, useScroll, useTransform } from "motion/react"

import { EDITORIAL_EASE, MOTION_DURATION } from "@/lib/motion"

/**
 * A block that moves with the page, not just when it arrives.
 *
 * `Reveal` (in `@/components/motion`) fades a section in once and is then
 * finished — the right thing for a dashboard panel, and the reason the old
 * landing page felt static: four identical entrances and nothing after.
 *
 * This keeps a slow parallax bound to scroll position for as long as the
 * block is on screen, so the page has a sense of depth while it is being
 * read rather than only at the moment each section appears. The range is
 * deliberately small — ±28px across a full viewport of travel. Anything
 * larger fights the reader's own scrolling and turns text into something
 * that has to be chased.
 *
 * Under `prefers-reduced-motion` this is a plain `div`: no entrance, no
 * parallax, no scroll listener attached at all.
 */
export function ScrollReveal({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const prefersReducedMotion = useReducedMotion()

  // `offset` measures from the block entering the bottom of the viewport to
  // it leaving the top, which is the whole window in which parallax can be
  // seen at all.
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end start"],
  })
  const y = useTransform(scrollYProgress, [0, 1], [28, -28])

  if (prefersReducedMotion) {
    return (
      <div ref={ref} className={className}>
        {children}
      </div>
    )
  }

  return (
    <motion.div
      ref={ref}
      className={className}
      style={{ y }}
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true, margin: "0px 0px -12% 0px" }}
      transition={{ duration: MOTION_DURATION.panel, ease: EDITORIAL_EASE }}
    >
      {children}
    </motion.div>
  )
}
