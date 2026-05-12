import { type ReactNode } from "react"
import { motion, useReducedMotion } from "motion/react"

type PressFeedbackProps = {
  children: ReactNode
  className?: string
  scale?: number
}

const EDITORIAL_EASE = [0.22, 1, 0.36, 1] as const

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
      transition={{ duration: 0.12, ease: EDITORIAL_EASE }}
    >
      {children}
    </motion.div>
  )
}
