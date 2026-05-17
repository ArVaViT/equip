import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-primary-foreground hover:bg-primary/90",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
        outline: "text-foreground",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/90",
        success:
          "border-transparent bg-success text-success-foreground hover:bg-success/90",
        warning:
          "border-transparent bg-warning text-warning-foreground hover:bg-warning/90",
        info: "border-transparent bg-info text-info-foreground hover:bg-info/90",
        muted:
          "border-transparent bg-muted text-muted-foreground hover:bg-muted/80",
        accent:
          "border-transparent bg-accent text-accent-foreground hover:bg-accent/80",
        successSubtle: "border-transparent bg-success/15 text-success",
        warningSubtle: "border-transparent bg-warning/15 text-warning",
        infoSubtle: "border-transparent bg-info/15 text-info",
        destructiveSubtle:
          "border-transparent bg-destructive/15 text-destructive",
        primarySubtle: "border-transparent bg-primary/15 text-primary",
      },
    },
    defaultVariants: { variant: "default" },
  },
)

interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}
