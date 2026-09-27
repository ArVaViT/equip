import { forwardRef, type HTMLAttributes, type ReactNode } from "react"
import { motion, useReducedMotion, type HTMLMotionProps } from "motion/react"
import { EDITORIAL_EASE, MOTION_DURATION } from "@/lib/motion"

type PressFeedbackProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode
  className?: string
  scale?: number
}

/**
 * A small press-in on tap.
 *
 * It forwards its ref and every other prop to the element it renders. It
 * did neither until 2026-09-27, and it sits inside `TooltipTrigger asChild`
 * in the header: Radix's `Slot` hands its child the ref it anchors the
 * tooltip to and the pointer handlers that open it, and this component
 * dropped all of them — so the tooltips on the menu buttons never opened,
 * in either motion mode (React said so only in development: «Function
 * components cannot be given refs»).
 */
export const PressFeedback = forwardRef<HTMLDivElement, PressFeedbackProps>(
  function PressFeedback({ children, className, scale = 0.97, ...rest }, ref) {
    const prefersReducedMotion = useReducedMotion()

    if (prefersReducedMotion) {
      return (
        <div ref={ref} className={className} {...rest}>
          {children}
        </div>
      )
    }

    return (
      <motion.div
        ref={ref}
        className={className}
        whileTap={{ scale }}
        transition={{ duration: MOTION_DURATION.fast, ease: EDITORIAL_EASE }}
        // The DOM handlers a trigger passes down are the same events motion
        // listens to; its own prop types only differ in the animation ones,
        // which nobody passes here.
        {...(rest as HTMLMotionProps<"div">)}
      >
        {children}
      </motion.div>
    )
  },
)
