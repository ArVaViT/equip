import { forwardRef, type HTMLAttributes, type ReactNode } from "react"
import { cn } from "@/lib/utils"

type PressFeedbackProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode
  className?: string
}

/**
 * A small press-in on tap: scale 0.97 over `duration-fast` on the editorial
 * curve, and nothing at all under `prefers-reduced-motion`.
 *
 * Plain CSS, not `motion`. This sits in the header, which every page loads
 * eagerly, and a `motion.div` here was what put the whole motion runtime
 * (about 41 KB gzip) in the first load of every visitor — anonymous ones
 * included — for one transform on press (2026-09-30 audit, F1). `:active`
 * holds on the wrapper while the button inside is pressed, so the effect
 * is the same.
 *
 * It forwards its ref and every other prop to the element it renders. It
 * did neither until 2026-09-27, and it sits inside `TooltipTrigger asChild`
 * in the header: Radix's `Slot` hands its child the ref it anchors the
 * tooltip to and the pointer handlers that open it, and this component
 * dropped all of them — so the tooltips on the menu buttons never opened
 * («Function components cannot be given refs»).
 */
export const PressFeedback = forwardRef<HTMLDivElement, PressFeedbackProps>(
  function PressFeedback({ children, className, ...rest }, ref) {
    return (
      <div
        ref={ref}
        className={cn(
          "transition-transform duration-fast ease-editorial motion-safe:active:scale-[0.97]",
          className,
        )}
        {...rest}
      >
        {children}
      </div>
    )
  },
)
