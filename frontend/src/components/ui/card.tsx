import * as React from "react"
import { cn } from "@/lib/utils"

const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      // 2026-06-02 UX call (Vadym): default Card drops the resting
      // border — bg-surface-elevated alone separates from the page,
      // and the all-bordered look read as cheap HTML chrome. Call
      // sites that need a frame (selected state, dnd-drop zone,
      // hover handoff via `hover:border-primary/40`) opt back in
      // explicitly via `className="border border-edge"`.
      //
      // `transition-[border-color,background-color]` (kept) so the
      // opt-in border-tint transitions stay smooth.
      //
      // ADR-0011 Wave 3 — migrated from `border-border bg-card
      // text-card-foreground` to the v2 semantic vocabulary
      // (`bg-surface-elevated text-ink`). Identical pixels today via
      // the tokens-bridge layer; flips to OKLCH in Wave 9 with no
      // code change.
      "rounded-md bg-surface-elevated text-ink shadow-none transition-[border-color,background-color] duration-200 ease-editorial",
      className
    )}
    {...props}
  />
))
Card.displayName = "Card"

const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex flex-col space-y-1.5 p-5", className)}
    {...props}
  />
))
CardHeader.displayName = "CardHeader"

const CardTitle = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h3
    ref={ref}
    className={cn(
      "text-lg font-semibold leading-none tracking-tight",
      className
    )}
    {...props}
  />
))
CardTitle.displayName = "CardTitle"

const CardDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    // Wave 3 — text-muted-foreground -> text-ink-muted (semantic v2).
    className={cn("text-sm text-ink-muted", className)}
    {...props}
  />
))
CardDescription.displayName = "CardDescription"

const CardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("p-5 pt-0", className)} {...props} />
))
CardContent.displayName = "CardContent"

export { Card, CardHeader, CardTitle, CardDescription, CardContent }

