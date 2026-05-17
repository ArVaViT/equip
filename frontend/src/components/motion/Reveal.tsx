import { type ReactNode } from "react"
import { motion, useReducedMotion } from "motion/react"
import { EDITORIAL_EASE, MOTION_DURATION } from "@/lib/motion"

type RevealProps = {
  children: ReactNode
  className?: string
  y?: number
  once?: boolean
  amount?: number
}

export function Reveal({
  children,
  className,
  y = 16,
  once = true,
  amount = 0.15,
}: RevealProps) {
  const prefersReducedMotion = useReducedMotion()

  if (prefersReducedMotion) {
    return <div className={className}>{children}</div>
  }

  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once, amount }}
      transition={{ duration: MOTION_DURATION.slow, ease: EDITORIAL_EASE }}
    >
      {children}
    </motion.div>
  )
}
