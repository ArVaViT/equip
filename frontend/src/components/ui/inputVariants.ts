import { cva } from "class-variance-authority"

export const inputVariants = cva(
  "flex w-full rounded-md border border-input bg-background shadow-sm ring-offset-background transition-[color,box-shadow,border-color] duration-200 ease-editorial file:border-0 file:bg-transparent file:font-medium placeholder:text-muted-foreground/85 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/80 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 disabled:bg-muted/40 aria-[invalid=true]:border-destructive focus-visible:aria-[invalid=true]:ring-destructive/35 dark:shadow-none",
  {
    variants: {
      fieldSize: {
        /** Default forms — 40px. Mobile text-base prevents iOS zoom-on-focus. */
        default: "h-10 px-3 py-2 text-base sm:text-sm file:text-sm",
        /** Dense tables / gradebook — 36px. Mobile text-base prevents iOS zoom. */
        md: "h-9 px-3 py-2 text-base sm:text-sm file:text-sm",
        /** Editors / tight toolbars — 32px */
        sm: "h-8 px-2.5 py-1 text-xs file:text-xs",
        /** Auth / comfortable touch — 44px. Mobile text-base prevents iOS zoom. */
        lg: "h-11 px-3 py-2 text-base sm:text-sm file:text-sm",
      },
    },
    defaultVariants: {
      fieldSize: "default",
    },
  },
)
