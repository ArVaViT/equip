import type { LucideIcon } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { cn } from "@/lib/utils"

interface Props {
  label: string
  value: string | number
  icon: LucideIcon
  /**
   * `value-leading` (default): label + value on the left, dimmer icon on
   * the right (used for in-page progress/analytics summaries).
   * `icon-leading`: framed icon on the left, label + value on the right
   * (used for the admin overview row).
   */
  variant?: "value-leading" | "icon-leading"
  /**
   * Override the default value text styling. Use for compact composite
   * values that would look chunky at the default `text-2xl font-bold`
   * (e.g. "30/50/20" weight triples in the gradebook).
   */
  valueClassName?: string
  /**
   * Small line under the value, for when the number needs a word to stop
   * looking like a contradiction — e.g. the gradebook showing the weights
   * actually applied while the settings page shows a different pair.
   */
  hint?: string
}

/**
 * Single metric card shared by ProgressStats, TeacherAnalytics,
 * GradebookStats, and the admin OverviewStats row. Keeps spacing,
 * icon stroke-width, and typography consistent across the platform.
 */
export function StatCard({
  label,
  value,
  icon: Icon,
  variant = "value-leading",
  valueClassName,
  hint,
}: Props) {
  if (variant === "icon-leading") {
    return (
      <Card>
        <CardContent className="flex items-center gap-4 p-5">
          <div className="rounded-md bg-muted p-3">
            <Icon className="h-6 w-6 text-ink-muted" strokeWidth={1.75} aria-hidden />
          </div>
          <div>
            <p className="text-sm text-ink-muted">{label}</p>
            <p className={cn("text-2xl font-bold tabular-nums", valueClassName)}>{value}</p>
            {hint && <p className="mt-0.5 text-xs text-ink-muted">{hint}</p>}
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-ink-muted">{label}</p>
            <p className={cn("text-2xl font-bold tabular-nums mt-1", valueClassName)}>{value}</p>
            {hint && <p className="mt-0.5 text-xs text-ink-muted">{hint}</p>}
          </div>
          <Icon className="h-6 w-6 text-ink-muted/60" strokeWidth={1.75} aria-hidden />
        </div>
      </CardContent>
    </Card>
  )
}
