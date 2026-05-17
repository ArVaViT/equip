import { type ReactNode } from "react"
import { motion, useReducedMotion } from "motion/react"
import { EDITORIAL_EASE, MOTION_DURATION } from "@/lib/motion"

type PressFeedbackProps = {
  children: ReactNode
  className?: string
  scale?: number
}

export function PressFeedback({
  children,
  className,
  scale = 0.97,
}: PressFeedbackProps) {
  const prefersReducedMotion = useReducedMotion()

  if (prefersReducedMotion) {
    return <div className={className}>{children}</div>
  }

  return (
    <motion.div
      className={className}
      whileTap={{ scale }}
      transition={{ duration: MOTION_DURATION.instant, ease: EDITORIAL_EASE }}
    >
      {children}
    </motion.div>
  )
}
