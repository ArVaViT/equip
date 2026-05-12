import { type ReactNode } from "react"
import { motion, useReducedMotion } from "motion/react"

type HoverLiftProps = {
  children: ReactNode
  className?: string
  lift?: number
  press?: number
}

const EDITORIAL_EASE = [0.22, 1, 0.36, 1] as const

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
      transition={{ duration: 0.28, ease: EDITORIAL_EASE }}
    >
      {children}
    </motion.div>
  )
}
