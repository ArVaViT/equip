import { useRef, type ReactNode } from "react"
import { motion, useReducedMotion, useScroll, useTransform } from "motion/react"

/**
 * A frame that settles into place as it arrives, instead of sliding in flat.
 *
 * Both videos on the landing page are large rectangles, and a large
 * rectangle scrolling up from the bottom edge at full size reads as the
 * page running into a wall. Here the frame starts a little small and a
 * little dim and reaches its full size exactly as its centre reaches the
 * centre of the screen — which is also where the page's snap point holds
 * it, so the movement ends where the reader stops.
 *
 * Borrowed from claude.com/product, where the product frames do the same.
 * The range is deliberately short: 0.92 → 1. More than that and the video
 * visibly zooms, which is a trick rather than an arrival.
 *
 * Bound to scroll position, not to a one-off entrance, so scrolling back up
 * reverses it — the same rule as `ScrollReveal`. Under
 * `prefers-reduced-motion` it is a plain `div`.
 */
export function ScrollScale({ children, className }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const prefersReducedMotion = useReducedMotion()

  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "center center"],
  })
  const scale = useTransform(scrollYProgress, [0, 1], [0.92, 1])
  const opacity = useTransform(scrollYProgress, [0, 0.6], [0.35, 1])

  if (prefersReducedMotion) {
    return (
      <div ref={ref} className={className}>
        {children}
      </div>
    )
  }

  return (
    <motion.div ref={ref} className={className} style={{ scale, opacity }}>
      {children}
    </motion.div>
  )
}
