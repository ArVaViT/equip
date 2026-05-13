import { type ReactNode } from "react"
import { motion, useReducedMotion } from "motion/react"

type FadeInProps = {
  children: ReactNode
  delay?: number
  duration?: number
  y?: number
  className?: string
}

const EDITORIAL_EASE = [0.22, 1, 0.36, 1] as const

export function FadeIn({
  children,
  delay = 0,
  duration = 0.48,
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
