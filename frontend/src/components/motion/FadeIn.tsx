import { type ReactNode } from "react"
import { motion, useReducedMotion } from "motion/react"
import { EDITORIAL_EASE, MOTION_DURATION } from "@/lib/motion"

type FadeInProps = {
  children: ReactNode
  delay?: number
  duration?: number
  y?: number
  className?: string
}

export function FadeIn({
  children,
  delay = 0,
  duration = MOTION_DURATION.entrance,
  y = 8,
  className,
}: FadeInProps) {
  const prefersReducedMotion = useReducedMotion()

  if (prefersReducedMotion) {
    return <div className={className}>{children}</div>
  }

  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration, delay, ease: EDITORIAL_EASE }}
    >
      {children}
    </motion.div>
  )
}
