import { cva } from "class-variance-authority"

export const textareaVariants = cva(
  "flex w-full rounded-md border border-input bg-background shadow-sm ring-offset-background transition-[color,box-shadow,border-color] duration-200 ease-editorial placeholder:text-muted-foreground/85 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/80 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 disabled:bg-muted/40 aria-[invalid=true]:border-destructive focus-visible:aria-[invalid=true]:ring-destructive/35 dark:shadow-none resize-y",
  {
    variants: {
      fieldSize: {
        default: "min-h-[80px] px-3 py-2 text-base sm:text-sm",
        sm: "min-h-[60px] px-3 py-2 text-base sm:text-sm",
        md: "min-h-[72px] px-3 py-2 text-base sm:text-sm",
        lg: "min-h-[96px] px-3 py-2 text-base sm:text-sm",
      },
    },
    defaultVariants: {
      fieldSize: "default",
    },
  },
)
