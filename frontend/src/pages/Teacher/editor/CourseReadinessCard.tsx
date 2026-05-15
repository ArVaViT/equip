import { useState } from "react"
import { useTranslation } from "react-i18next"
import { motion, useReducedMotion } from "motion/react"
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Circle,
  Info,
  Sparkles,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import type {
  ReadinessAction,
  ReadinessCheck,
  ReadinessReport,
  ReadinessSeverity,
} from "@/services/courseReadiness"

interface Props {
  report: ReadinessReport | null
  loading: boolean
  /** Called when the teacher clicks "Fix" on a check that has an action.
   *  Parent owns the routing/modal behaviour. */
  onFix?: (action: ReadinessAction, check: ReadinessCheck) => void
}

const SEVERITY_ORDER: ReadinessSeverity[] = ["critical", "recommended", "polish"]

const SEVERITY_META: Record<
  ReadinessSeverity,
  { icon: typeof AlertTriangle; tone: "destructive" | "warning" | "muted"; labelKey: string }
> = {
  critical: { icon: AlertTriangle, tone: "destructive", labelKey: "courseReadiness.severity.critical" },
  recommended: { icon: Info, tone: "warning", labelKey: "courseReadiness.severity.recommended" },
  polish: { icon: Sparkles, tone: "muted", labelKey: "courseReadiness.severity.polish" },
}

const TONE_CLASS: Record<"destructive" | "warning" | "muted", string> = {
  destructive: "text-destructive",
  warning: "text-warning",
  muted: "text-muted-foreground",
}

/**
 * Course-readiness checklist card.
 *
 * Sits above the modules list on the course editor. Reads as a compact
 * editorial pill when collapsed; expands into a grouped checklist with
 * one-click "Fix" deep-links per item. Pure presentation — every action
 * routes back to the parent via ``onFix``, which keeps modal control
 * + navigation in one place (CourseEditor).
 */
export function CourseReadinessCard({ report, loading, onFix }: Props) {
  const { t } = useTranslation()
  const prefersReducedMotion = useReducedMotion()
  const [open, setOpen] = useState(false)

  if (loading) {
    return (
      <section
        className="mb-6 overflow-hidden rounded-md border border-border bg-card"
        aria-busy="true"
      >
        <div className="flex items-center gap-4 px-5 py-4">
          <Skeleton className="h-10 w-10 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-3 w-32" />
          </div>
          <Skeleton className="h-8 w-24 rounded-md" />
        </div>
      </section>
    )
  }

  if (!report) return null

  const failing = report.checks.filter((c) => !c.passed)
  const allPass = failing.length === 0
  const headerTone: "destructive" | "warning" | "success" =
    report.critical_failing > 0
      ? "destructive"
      : failing.some((c) => c.severity === "recommended")
        ? "warning"
        : "success"

  const headerToneClasses: Record<typeof headerTone, string> = {
    destructive: "border-destructive/30 bg-destructive/[0.04]",
    warning: "border-warning/30 bg-warning/[0.04]",
    success: "border-success/30 bg-success/[0.04]",
  }
  const ringForeground: Record<typeof headerTone, string> = {
    destructive: "stroke-destructive",
    warning: "stroke-warning",
    success: "stroke-success",
  }

  return (
    <section
      aria-label={t("courseReadiness.title")}
      className={cn(
        "mb-6 overflow-hidden rounded-md border bg-card transition-colors",
        headerToneClasses[headerTone],
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-4 px-5 py-4 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        <ScoreRing
          score={report.score}
          tone={headerTone}
          ringClass={ringForeground[headerTone]}
          prefersReducedMotion={Boolean(prefersReducedMotion)}
        />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            {t("courseReadiness.title")}
          </p>
          <p className="mt-0.5 font-serif text-base font-semibold tracking-tight text-foreground">
            {allPass
              ? t("courseReadiness.allPassed")
              : t("courseReadiness.summary", {
                  passing: report.passing,
                  total: report.total,
                })}
          </p>
          {!allPass && report.critical_failing > 0 && (
            <p className="mt-0.5 text-xs text-destructive">
              {t("courseReadiness.criticalCount", { count: report.critical_failing })}
            </p>
          )}
        </div>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-180",
          )}
          strokeWidth={1.75}
          aria-hidden
        />
      </button>

      {open && (
        <div className="border-t border-border bg-card px-5 py-5">
          {SEVERITY_ORDER.map((severity) => {
            const groupChecks = report.checks.filter((c) => c.severity === severity)
            if (groupChecks.length === 0) return null
            return (
              <CheckGroup
                key={severity}
                severity={severity}
                checks={groupChecks}
                onFix={onFix}
              />
            )
          })}
        </div>
      )}
    </section>
  )
}

function ScoreRing({
  score,
  tone,
  ringClass,
  prefersReducedMotion,
}: {
  score: number
  tone: "destructive" | "warning" | "success"
  ringClass: string
  prefersReducedMotion: boolean
}) {
  // Single 40px ring; CSS-only stroke-dasharray animates from 0 to ``score``.
  const radius = 16
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - score / 100)
  const animProps = prefersReducedMotion
    ? { strokeDashoffset: offset }
    : { initial: { strokeDashoffset: circumference }, animate: { strokeDashoffset: offset } }
  const toneTextClass = {
    destructive: "text-destructive",
    warning: "text-warning",
    success: "text-success",
  }[tone]
  return (
    <div className="relative flex h-10 w-10 shrink-0 items-center justify-center">
      <svg width={40} height={40} className="-rotate-90" aria-hidden>
        <circle
          cx={20}
          cy={20}
          r={radius}
          className="stroke-muted"
          strokeWidth={3}
          fill="none"
        />
        <motion.circle
          cx={20}
          cy={20}
          r={radius}
          className={cn(ringClass)}
          strokeWidth={3}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          {...animProps}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        />
      </svg>
      <span className={cn("absolute text-xs font-semibold tabular-nums", toneTextClass)}>
        {score}
      </span>
    </div>
  )
}

function CheckGroup({
  severity,
  checks,
  onFix,
}: {
  severity: ReadinessSeverity
  checks: ReadinessCheck[]
  onFix?: (action: ReadinessAction, check: ReadinessCheck) => void
}) {
  const { t } = useTranslation()
  const meta = SEVERITY_META[severity]
  const Icon = meta.icon
  return (
    <div className="mb-5 last:mb-0">
      <div className="mb-3 flex items-center gap-2">
        <Icon
          className={cn("h-4 w-4 shrink-0", TONE_CLASS[meta.tone])}
          strokeWidth={1.75}
          aria-hidden
        />
        <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          {t(meta.labelKey)}
        </h3>
      </div>
      <ul className="space-y-2">
        {checks.map((check) => (
          <CheckRow key={check.id} check={check} onFix={onFix} />
        ))}
      </ul>
    </div>
  )
}

function CheckRow({
  check,
  onFix,
}: {
  check: ReadinessCheck
  onFix?: (action: ReadinessAction, check: ReadinessCheck) => void
}) {
  const { t } = useTranslation()
  // Render message with subject title interpolated. The backend's i18n
  // keys all accept ``{{title}}`` so per-chapter / per-module checks can
  // include the entity name natively.
  const message = t(check.message_key, {
    defaultValue: check.message_key,
    title: check.subject?.title,
  })
  return (
    <li className="flex items-start gap-3 text-sm">
      {check.passed ? (
        <CheckCircle2
          className="mt-0.5 h-4 w-4 shrink-0 text-success"
          strokeWidth={1.75}
          aria-hidden
        />
      ) : (
        <Circle
          className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/50"
          strokeWidth={1.75}
          aria-hidden
        />
      )}
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            "text-foreground text-wrap-safe",
            check.passed && "text-muted-foreground line-through decoration-muted-foreground/40",
          )}
        >
          {message}
        </p>
      </div>
      {!check.passed && check.action && onFix && (
        <Button
          variant="ghost"
          size="sm"
          className="h-7 shrink-0 px-2 text-xs"
          onClick={() => onFix(check.action!, check)}
        >
          {t("courseReadiness.fix")}
        </Button>
      )}
    </li>
  )
}
