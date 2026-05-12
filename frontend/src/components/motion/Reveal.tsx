import { type ReactNode } from "react"
import { motion, useReducedMotion } from "motion/react"

type RevealProps = {
  children: ReactNode
  className?: string
  y?: number
  once?: boolean
  amount?: number
}

const EDITORIAL_EASE = [0.22, 1, 0.36, 1] as const

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
      transition={{ duration: 0.55, ease: EDITORIAL_EASE }}
    >
      {children}
    </motion.div>
  )
}
