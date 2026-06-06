import * as React from "react"
import { cn } from "@/lib/utils"

const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      // 2026-06-06: resting border RESTORED (Vadym: "a couple days ago
      // there were no white lines, everything was normal"). Removing the
      // border (#696) left a near-white surface-elevated (99% L) fill
      // floating on the warm 97% L page — that read as "white panels", the
      // exact thing being complained about. The bordered card (the state
      // through #662) is the look that read as normal: a clear --edge (87% L)
      // hairline frames the card instead of letting the fill float.
      //
      // `transition-[border-color,background-color]` keeps the hover
      // border-tint handoff smooth (call sites use `hover:border-primary/40`).
      //
      // ADR-0011 Wave 3 — v2 semantic vocabulary (`border-edge
      // bg-surface-elevated text-ink`), bridged to --border/--card today;
      // flips to OKLCH in Wave 9 with no code change.
      "rounded-md border border-edge bg-surface-elevated text-ink shadow-none transition-[border-color,background-color] duration-200 ease-editorial",
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

