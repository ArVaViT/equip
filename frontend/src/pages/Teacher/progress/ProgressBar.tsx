/** Horizontal progress bar with tone steps (red → amber → primary → green). */
export function ProgressBar({
  value,
  className = "",
}: {
  value: number
  className?: string
}) {
  const color =
    value >= 100
      ? "bg-success"
      : value >= 60
        ? "bg-brand"
        : value >= 30
          ? "bg-warning"
          : "bg-destructive"

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div className="h-2 max-w-[120px] flex-1 rounded-full bg-muted">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${Math.min(value, 100)}%` }}
        />
      </div>
      <span className="w-10 text-right text-xs font-medium tabular-nums">
        {value}%
      </span>
    </div>
  )
}

/** Small percentage pill with tone based on score. `null` renders an em-dash. */
export function ScoreBadge({ value }: { value: number | null }) {
  if (value === null) return <span className="text-xs text-ink-muted">—</span>
  const color =
    value >= 90
      ? "bg-success/15 text-success"
      : value >= 70
        ? "bg-info/15 text-info"
        : value >= 50
          ? "bg-warning/15 text-warning"
          : "bg-destructive/15 text-destructive"
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>
      {value}%
    </span>
  )
}
