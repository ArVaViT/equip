import { useCallback, useEffect, useState } from "react"
import { useParams, useSearchParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/patterns"
import { FileText, Loader2, Printer } from "lucide-react"
import { gradesService } from "@/services/grades"
import type { GradeSheet } from "@/types"
import { printedResult } from "./resultLabel"
import { formatPercent } from "@/i18n/number"
import "./print.css"

/** `dd.mm.yyyy` — the form every Russian-language document uses. */
function formatDate(iso: string | null): string {
  if (!iso) return "—"
  const d = new Date(iso)
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}`
}

/**
 * The printable ведомость.
 *
 * Everything on this page comes off the frozen sheet — the grades, the names,
 * the поток, the school, the teacher, the hours. Nothing is recomputed or
 * looked up, which is the entire point: a director signs this and files it,
 * and the paper in the folder has to still match the database in five years.
 *
 * Printing is the browser's own Print → Save as PDF. No paid service, no
 * server-side renderer — one less thing to keep running, and one less place
 * for a document to be generated differently than it was displayed.
 */
function VedomostPage() {
  const { t } = useTranslation()
  const { courseId } = useParams<{ courseId: string }>()
  const [params] = useSearchParams()
  const cohortId = params.get("cohort_id")

  const [sheet, setSheet] = useState<GradeSheet | null>(null)
  const [loading, setLoading] = useState(true)
  const [closing, setClosing] = useState(false)

  const load = useCallback(() => {
    if (!courseId) return
    setLoading(true)
    gradesService
      .getGradeSheet(courseId, cohortId)
      .then(setSheet)
      .catch(() => setSheet(null))
      .finally(() => setLoading(false))
  }, [courseId, cohortId])

  useEffect(load, [load])

  const close = async () => {
    if (!courseId) return
    setClosing(true)
    try {
      setSheet(await gradesService.closeGradeSheet(courseId, cohortId))
    } finally {
      setClosing(false)
    }
  }

  if (loading) {
    return (
      <div className="container mx-auto flex items-center gap-2 px-4 py-10 text-sm text-ink-muted">
        <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />
        {t("vedomost.loading")}
      </div>
    )
  }

  if (!sheet) {
    return (
      <div className="container mx-auto max-w-2xl px-4 py-10">
        <EmptyState
          icon={<FileText strokeWidth={1.75} aria-hidden />}
          title={t("vedomost.notClosedTitle")}
          description={t("vedomost.notClosedBody")}
          action={
            <Button onClick={close} disabled={closing}>
              {closing && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" strokeWidth={1.75} />}
              {t("vedomost.close")}
            </Button>
          }
        />
      </div>
    )
  }

  return (
    <div className="container mx-auto max-w-4xl px-4 py-6">
      <div className="no-print mb-6 flex items-center justify-between gap-3">
        <p className="text-sm text-ink-muted">
          {t("vedomost.closedOn", { date: formatDate(sheet.finalized_at) })}
        </p>
        <Button onClick={() => window.print()}>
          <Printer className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
          {t("vedomost.print")}
        </Button>
      </div>

      <article className="vedomost bg-surface p-8">
        <header className="mb-6 text-center">
          <p className="text-base font-semibold uppercase tracking-wide">
            {sheet.school_name ?? t("vedomost.schoolUnnamed")}
          </p>
          {sheet.school_city && <p className="text-sm">{sheet.school_city}</p>}
          <h1 className="mt-6 font-serif text-xl font-bold">{t("vedomost.title")}</h1>
        </header>

        <dl className="mb-6 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="font-medium">{t("vedomost.course")}</dt>
          <dd>{sheet.course_title ?? sheet.course_id}</dd>
          <dt className="font-medium">{t("vedomost.teacher")}</dt>
          <dd>{sheet.teacher_name ?? "—"}</dd>
          <dt className="font-medium">{t("vedomost.cohort")}</dt>
          <dd>
            {sheet.cohort_name ?? t("vedomost.noCohort")}
            {sheet.cohort_start && (
              <span className="text-ink-muted">
                {" "}
                ({formatDate(sheet.cohort_start)} — {formatDate(sheet.cohort_end)})
              </span>
            )}
          </dd>
          {sheet.academic_hours !== null && (
            <>
              <dt className="font-medium">{t("vedomost.hours")}</dt>
              <dd>{sheet.academic_hours}</dd>
            </>
          )}
          <dt className="font-medium">{t("vedomost.passLine")}</dt>
          <dd>{sheet.pass_threshold ? formatPercent(Number(sheet.pass_threshold), 0) : "—"}</dd>
        </dl>

        {/* A document that changed after signature has to say so on its face. */}
        {sheet.corrects_sheet_id && (
          <p className="marker mb-4 px-3 py-2 text-sm">
            {t("vedomost.wasReopened", { reason: sheet.correction_reason ?? "" })}
          </p>
        )}

        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-y-2 border-ink">
              <th className="w-10 py-2 text-left font-medium">№</th>
              <th className="py-2 text-left font-medium">{t("vedomost.student")}</th>
              <th className="w-40 py-2 text-left font-medium">{t("vedomost.resultHeader")}</th>
            </tr>
          </thead>
          <tbody>
            {sheet.rows.map((row, index) => {
              const result = printedResult(row, t)
              return (
                <tr key={row.student_id} className="border-b">
                  <td className="py-1.5">{index + 1}</td>
                  <td className="py-1.5">{row.student_name ?? "—"}</td>
                  <td className="py-1.5">
                    {result.text}
                    {/* The glyph a signing director should not have to ask about. */}
                    {result.isOverride && (
                      <span className="marker ml-2 px-1 text-xs">{t("vedomost.byHand")}</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>

        {sheet.rows.some((r) => r.is_override) && (
          <p className="mt-3 text-xs text-ink-muted">{t("vedomost.byHandLegend")}</p>
        )}

        <div className="signatures mt-12 grid grid-cols-2 gap-12 text-sm">
          <div>
            <div className="border-b border-ink pb-8" />
            <p className="mt-1">{t("vedomost.signTeacher")}</p>
          </div>
          <div>
            <div className="border-b border-ink pb-8" />
            <p className="mt-1">{t("vedomost.signDirector")}</p>
          </div>
        </div>

        <p className="mt-8 text-xs text-ink-muted">
          {t("vedomost.closedOn", { date: formatDate(sheet.finalized_at) })}
        </p>
      </article>
    </div>
  )
}

export default VedomostPage
