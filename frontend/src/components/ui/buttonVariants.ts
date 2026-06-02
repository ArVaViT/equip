import { cva } from "class-variance-authority"

export const buttonVariants = cva(
  // Disabled state uses explicit muted tokens instead of ``opacity-50``.
  // ``opacity-50`` on a dark-mode primary button (lavender at 50%
  // luminance on top of a near-black surface) collapses contrast to
  // sub-AA and effectively makes the button — and any spinner / icon
  // inside — invisible. The token-based approach gives a deliberate
  // disabled colour that the design system controls per theme.
  //
  // ADR-0011 Wave 3 — migrated to the v2 semantic palette via the
  // tokens-bridge layer. Primary CTA → ``brand`` (the v2 name for
  // the violet brand color; v1's ``accent`` is sage and stays
  // available under that legacy name). Outline / ghost reach for the
  // sage ``heritage`` palette. Disabled keeps ``muted`` (no v2
  // equivalent yet — that's wave 4's form-primitives surface).
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-[color,box-shadow,transform] duration-150 ease-editorial focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:bg-muted disabled:text-muted-foreground disabled:hover:bg-muted",
  {
    variants: {
      variant: {
        default: "bg-brand text-brand-foreground hover:bg-brand/90",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline:
          "border border-edge-strong bg-surface hover:bg-heritage hover:text-ink",
        secondary:
          "bg-brand-quiet text-ink hover:bg-brand-quiet/80",
        ghost: "hover:bg-heritage hover:text-ink",
        link: "text-brand underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
        lg: "h-11 rounded-md px-8",
        icon: "h-10 w-10",
      },
    },
    compoundVariants: [
      {
        variant: ["default", "destructive", "outline", "secondary", "ghost"],
        class: "active:scale-[0.985]",
      },
      {
        variant: "link",
        class: "active:scale-100 active:opacity-80",
      },
    ],
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
)
