import { type ReactNode } from "react"
import { motion, useReducedMotion } from "motion/react"
import { EDITORIAL_EASE, MOTION_DURATION } from "@/lib/motion"

type HoverLiftProps = {
  children: ReactNode
  className?: string
  lift?: number
  press?: number
}

export function HoverLift({
  children,
  className,
  lift = 2,
  press = 0,
}: HoverLiftProps) {
  const prefersReducedMotion = useReducedMotion()

  if (prefersReducedMotion) {
    return <div className={className}>{children}</div>
  }

  return (
    <motion.div
      className={className}
      whileHover={{ y: -lift }}
      whileTap={press ? { y: press } : undefined}
      transition={{ duration: MOTION_DURATION.base, ease: EDITORIAL_EASE }}
    >
      {children}
    </motion.div>
  )
}
