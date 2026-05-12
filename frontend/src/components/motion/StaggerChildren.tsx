import { Children, type ReactNode } from "react"
import { motion, useReducedMotion } from "motion/react"

type StaggerChildrenProps = {
  children: ReactNode
  stagger?: number
  duration?: number
  y?: number
  className?: string
}

const EDITORIAL_EASE = [0.22, 1, 0.36, 1] as const

export function StaggerChildren({
  children,
  stagger = 0.045,
  duration = 0.48,
  y = 8,
  className,
}: StaggerChildrenProps) {
  const prefersReducedMotion = useReducedMotion()
  const items = Children.toArray(children)

  if (prefersReducedMotion) {
    return <div className={className}>{children}</div>
  }

  return (
    <motion.div
      className={className}
      initial="hidden"
      animate="visible"
      variants={{
        hidden: {},
        visible: { transition: { staggerChildren: stagger } },
      }}
    >
      {items.map((child, i) => (
        <motion.div
          key={i}
          variants={{
            hidden: { opacity: 0, y },
            visible: {
              opacity: 1,
              y: 0,
              transition: { duration, ease: EDITORIAL_EASE },
            },
          }}
        >
          {child}
        </motion.div>
      ))}
    </motion.div>
  )
}
