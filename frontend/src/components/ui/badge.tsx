import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

// ADR-0011 Wave 6 — editorial primitives migration.
// Migrated to v2 vocabulary: primary -> brand, secondary -> brand-quiet,
// accent -> heritage, foreground -> ink, ring-brand -> ring-brand.
// destructive / success / warning / info / muted stay on v1 — no v2
// equivalents are in the bridge or tailwind config yet (the tokens-v2
// CSS has --color-{success,warning,danger,info} but they aren't aliased
// in tailwind.config.js, so the v1 classes are still the only working
// path for those semantic tones).
const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-brand text-brand-foreground hover:bg-brand/90",
        secondary:
          "border-transparent bg-brand-quiet text-ink hover:bg-brand-quiet/80",
        outline: "text-ink",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/90",
        success:
          "border-transparent bg-success text-success-foreground hover:bg-success/90",
        warning:
          "border-transparent bg-warning text-warning-foreground hover:bg-warning/90",
        info: "border-transparent bg-info text-info-foreground hover:bg-info/90",
        muted:
          "border-transparent bg-muted text-ink-muted hover:bg-muted/80",
        accent:
          "border-transparent bg-heritage text-ink hover:bg-heritage/80",
        successSubtle: "border-transparent bg-success/15 text-success-ink",
        warningSubtle: "border-transparent bg-warning/15 text-warning-ink",
        infoSubtle: "border-transparent bg-info/15 text-info-ink",
        destructiveSubtle:
          "border-transparent bg-destructive/15 text-destructive-ink",
        primarySubtle: "border-transparent bg-brand/15 text-brand-ink",
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
