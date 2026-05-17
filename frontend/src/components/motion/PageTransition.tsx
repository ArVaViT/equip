import { type ReactNode } from "react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { EDITORIAL_EASE, MOTION_DURATION } from "@/lib/motion"

type PageTransitionProps = {
  routeKey: string
  children: ReactNode
}

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
        transition={{ duration: MOTION_DURATION.base, ease: EDITORIAL_EASE }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  )
}
