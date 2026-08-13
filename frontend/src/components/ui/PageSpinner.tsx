import { useTranslation } from "react-i18next"

interface PageSpinnerProps {
  /** Variants:
   *  - `page`: route-level fallback, centered with generous vertical padding
   *  - `screen`: full-viewport loader used during app bootstrap
   *  - `section`: in-card/in-section loader, smaller spinner and padding
   *  - `inline`: bare spinner (no wrapper) for one-off layouts */
  variant?: "page" | "screen" | "section" | "inline"
  /** Optional helper label shown under the spinner (screen variant only).
   *  Also used as the accessible name announced to screen readers — when
   *  `label` is omitted we still announce a localized generic "Loading"
   *  so AT users know a fetch is in progress instead of meeting an empty
   *  region. */
  label?: string
}

// One shared spinner, replacing the hand-rolled
// `animate-spin rounded-full border-* border-brand border-t-transparent`.
//
// WHICH LOADING TREATMENT TO USE
// ------------------------------
// The product has three, and all three are correct — for different things.
// What was missing was any statement of which goes where, so the choice was
// whichever the neighbouring file happened to make. Counted: 121 `<Skeleton>`,
// 21 `<PageSpinner>`, `Loader2` in 40 files.
//
//   `<Skeleton>`   — the shape of the content is known. Use it, always, in
//                    preference to a spinner. It is not a nicer spinner; it is
//                    a promise about layout, so the content lands where the
//                    placeholder was and nothing jumps. The reading surface
//                    has `<ReadingSkeleton>` for exactly this reason.
//   `Loader2`      — inside a button, while an action the user just started is
//                    in flight. The label stays; the icon spins beside it.
//   `<PageSpinner>` — the shape is genuinely unknown: a route-level fallback
//                    before the lazy chunk has told us what page this is, or
//                    app bootstrap. If you can draw the shape, draw it.
//
// Seven `variant="section"` call sites remain where the shape *is* knowable.
// They are a to-do, not a pattern to copy.
//
// `role="status"` + `aria-live="polite"` lets screen readers announce
// the load state without interrupting whatever the user was doing. The
// rotating ring itself is decorative — meaning lives in the label, which
// is always available to AT (via `aria-label`) even when it's not shown.
export default function PageSpinner({ variant = "page", label }: PageSpinnerProps) {
  const { t } = useTranslation()
  const accessibleLabel = label ?? t("common.loadingAccessible")

  if (variant === "screen") {
    return (
      <div className="flex items-center justify-center min-h-screen bg-surface">
        <div
          role="status"
          aria-live="polite"
          aria-label={accessibleLabel}
          className="flex flex-col items-center gap-4"
        >
          <div
            aria-hidden="true"
            className="h-10 w-10 animate-spin rounded-full border-[3px] border-brand border-t-transparent"
          />
          {label && <span className="text-sm text-ink-muted">{label}</span>}
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
          className="h-6 w-6 animate-spin rounded-full border-2 border-brand border-t-transparent"
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
        className="h-8 w-8 animate-spin rounded-full border-4 border-brand border-t-transparent"
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
        className="h-8 w-8 animate-spin rounded-full border-4 border-brand border-t-transparent"
      />
    </div>
  )
}
