import * as React from "react"
import { cn } from "@/lib/utils"

const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      // 2026-06-06: resting border is THEME-SPECIFIC (border in light,
      // transparent in dark) — the two themes fail oppositely:
      //   LIGHT — a borderless near-white surface-elevated (99% L) fill on
      //           the warm 97% L page floats as a "white panel" (#696's bug).
      //           Needs the --edge (87% L) hairline to read as a card.
      //   DARK  — a 19% L border around a 12% L card on the 9% L page outlines
      //           every card into an ugly "HTML-table grid". Dark separates by
      //           elevation (the lighter fill), not by a line → border-transparent.
      //
      // `transition-[border-color,background-color]` keeps the hover
      // border-tint handoff smooth (call sites use `hover:border-primary/40`).
      // Those hover/selected/dnd opt-ins set their own border color and so
      // still show in dark, which is intended (a deliberate frame, not a grid).
      //
      // ADR-0011 Wave 3 — v2 semantic vocabulary (`border-edge
      // bg-surface-elevated text-ink`), bridged to --border/--card today.
      "rounded-md border border-edge bg-surface-elevated text-ink shadow-none transition-[border-color,background-color] duration-200 ease-editorial dark:border-transparent",
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

