import { Children, type ReactNode } from "react"
import { motion, useReducedMotion } from "motion/react"
import { EDITORIAL_EASE, MOTION_DURATION } from "@/lib/motion"

type StaggerChildrenProps = {
  children: ReactNode
  stagger?: number
  duration?: number
  y?: number
  className?: string
}

export function StaggerChildren({
  children,
  stagger = 0.045,
  duration = MOTION_DURATION.entrance,
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
