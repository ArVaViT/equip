import { cva } from "class-variance-authority"

export const buttonVariants = cva(
  // Disabled state uses explicit muted tokens instead of ``opacity-50``.
  // ``opacity-50`` on a dark-mode primary button (lavender at 50%
  // luminance on top of a near-black surface) collapses contrast to
  // sub-AA and effectively makes the button — and any spinner / icon
  // inside — invisible. The token-based approach gives a deliberate
  // disabled colour that the design system controls per theme.
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-[color,box-shadow,transform] duration-150 ease-editorial focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:bg-muted disabled:text-muted-foreground disabled:hover:bg-muted",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline:
          "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
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
