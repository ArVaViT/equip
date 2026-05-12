import { type ReactNode } from "react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"

type PageTransitionProps = {
  routeKey: string
  children: ReactNode
}

const EDITORIAL_EASE = [0.22, 1, 0.36, 1] as const

export function PageTransition({ routeKey, children }: PageTransitionProps) {
  const prefersReducedMotion = useReducedMotion()

  if (prefersReducedMotion) {
    return <>{children}</>
  }

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={routeKey}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -4 }}
        transition={{ duration: 0.28, ease: EDITORIAL_EASE }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  )
}
