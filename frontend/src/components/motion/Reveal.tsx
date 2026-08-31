import type { ReactNode } from "react"
import { motion, useReducedMotion } from "motion/react"
import { EDITORIAL_EASE, MOTION_DURATION } from "@/lib/motion"

type RevealProps = {
  children: ReactNode
  /** Nudge in px the content travels while fading in. */
  y?: number
  /** Seconds to wait after the element enters view. Use sparingly. */
  delay?: number
  className?: string
}

/**
 * Content that arrives as you reach it.
 *
 * `StaggerChildren` orchestrates an entrance on mount, which is right for a
 * list that is already on screen. A long page needs the other half: sections
 * below the fold should not have animated while nobody was looking, and
 * should not stay invisible if the animation never runs.
 *
 * Hence `once: true` and a generous margin — the reveal fires slightly before
 * the section is fully in view, so a fast scroll never catches a blank block.
 * Under `prefers-reduced-motion` the content renders as plain markup with no
 * wrapper animation at all, which is also what a crawler and a screen reader
 * see.
 *
 * Duration is `panel` (400ms) from the shared scale rather than a bespoke
 * 550ms: this file's whole point is that there are three durations, not four.
 */
export function Reveal({ children, y = 12, delay = 0, className }: RevealProps) {
  const prefersReducedMotion = useReducedMotion()
  // A reveal starts at `opacity: 0` and waits for an observer to say the
  // element is in view. Where that observer does not exist — a very old
  // browser, a test renderer, anything that strips it — the wait never ends
  // and the section is simply never shown. Content that might not appear is
  // worse than content that appears without ceremony.
  const canObserve = typeof window !== "undefined" && "IntersectionObserver" in window

  if (prefersReducedMotion || !canObserve) {
    return <div className={className}>{children}</div>
  }

  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "0px 0px -12% 0px" }}
      transition={{ duration: MOTION_DURATION.panel, ease: EDITORIAL_EASE, delay }}
    >
      {children}
    </motion.div>
  )
}
