interface PageSpinnerProps {
  /** Variants:
   *  - `page`: route-level fallback, centered with generous vertical padding
   *  - `screen`: full-viewport loader used during app bootstrap
   *  - `section`: in-card/in-section loader, smaller spinner and padding
   *  - `inline`: bare spinner (no wrapper) for one-off layouts */
  variant?: "page" | "screen" | "section" | "inline"
  /** Optional helper label shown under the spinner (screen variant only).
   *  Also used as the accessible name announced to screen readers — when
   *  `label` is omitted we still announce a generic "Loading" so AT users
   *  know a fetch is in progress instead of meeting an empty region. */
  label?: string
}

// One shared spinner used everywhere we'd previously hand-rolled
// `animate-spin rounded-full border-* border-primary border-t-transparent`.
// Consolidating means theme tweaks (color, size) only need to land in one file.
//
// `role="status"` + `aria-live="polite"` lets screen readers announce
// the load state without interrupting whatever the user was doing. The
// rotating ring itself is decorative — meaning lives in the label, which
// is always available to AT (via `aria-label`) even when it's not shown.
export default function PageSpinner({ variant = "page", label }: PageSpinnerProps) {
  const accessibleLabel = label ?? "Loading"

  if (variant === "screen") {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <div
          role="status"
          aria-live="polite"
          aria-label={accessibleLabel}
          className="flex flex-col items-center gap-4"
        >
          <div
            aria-hidden="true"
            className="h-10 w-10 animate-spin rounded-full border-[3px] border-primary border-t-transparent"
          />
          {label && <span className="text-sm text-muted-foreground">{label}</span>}
        </div>
      </div>
    )
  }

  if (variant === "section") {
    return (
      <div
        role="status"
        aria-live="polite"
        aria-label={accessibleLabel}
        className="flex justify-center py-8"
      >
        <div
          aria-hidden="true"
          className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent"
        />
      </div>
    )
  }

  if (variant === "inline") {
    // The `inline` variant ships as a bare ring so callers can compose it
    // anywhere they need a spinner. The wrapping context (button, row,
    // modal) is responsible for any announcement — here we just mark the
    // glyph decorative.
    return (
      <div
        aria-hidden="true"
        className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"
      />
    )
  }

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={accessibleLabel}
      className="flex justify-center py-20"
    >
      <div
        aria-hidden="true"
        className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"
      />
    </div>
  )
}
