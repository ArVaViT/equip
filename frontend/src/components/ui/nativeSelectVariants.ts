import { cva } from "class-variance-authority"

/** Native `<select>` styling aligned with `inputVariants` (semantic tokens + focus ring). */
export const nativeSelectVariants = cva(
  "min-w-0 w-full cursor-pointer rounded-md border border-input bg-background shadow-sm ring-offset-background transition-[color,box-shadow,border-color] duration-200 ease-editorial focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/80 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:shadow-none",
  {
    variants: {
      fieldSize: {
        /** Match Input default — 40px. Mobile text-base prevents iOS zoom-on-focus. */
        default: "h-10 px-3 py-2 text-base sm:text-sm",
        /** Dense filters — 36px. Mobile text-base prevents iOS zoom. */
        md: "h-9 px-3 py-2 text-base sm:text-sm",
        /** Table row controls — 32px */
        sm: "h-8 px-2.5 py-1 text-xs",
        /** Bulk toolbar — ~28px */
        xs: "h-7 px-2 py-0.5 text-xs",
        /** Comfort — 44px. Mobile text-base prevents iOS zoom. */
        lg: "h-11 px-3 py-2 text-base sm:text-sm",
      },
    },
    defaultVariants: {
      fieldSize: "default",
    },
  },
)
