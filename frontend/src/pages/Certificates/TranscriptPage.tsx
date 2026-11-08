import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { ArrowLeft, Printer } from "lucide-react"

import { Button } from "@/components/ui/button"
import PageSpinner from "@/components/ui/PageSpinner"
import { ErrorState } from "@/components/patterns"
import { useAuth } from "@/context/useAuth"
import { useAsyncData } from "@/hooks/useAsyncData"
import { documentDay, formatDayLong } from "@/i18n/format"
import { getErrorDetail } from "@/lib/errorDetail"
import { coursesService } from "@/services/courses"
import type { Certificate } from "@/types"
import { DOCUMENT_LOCALE, mainSymbolScheme, schemeName, transcriptGrade } from "./transcriptGrade"
import "./transcript-print.css"

/**
 * Every course a student has completed, on one sheet: what a pastor asks for
 * before an ordination, and a school before it accepts a transfer.
 *
 * Only certificates actually issued, oldest first, each with the number a
 * reader can check at /verify. Everything on a line — the grade, «with
 * honors», the hours — is what was frozen onto that certificate when it was
 * issued (M6); nothing is recomputed, so a course graded under another scale
 * years ago still reads the way it was signed.
 *
 * English, like the certificate and the ведомость: documents on this platform
 * are English whatever the interface language, so the strings carry the same
 * English value in every catalogue.
 */
export default function TranscriptPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const { data, loading, error, refetch } = useAsyncData(() => coursesService.getMyCertificates(), [])

  if (loading) return <PageSpinner />
  if (error) {
    return (
      <div className="container mx-auto max-w-2xl px-4 py-16 text-center">
        <ErrorState
          description={getErrorDetail(error, t("certificates.document.loadFailed"))}
          action={
            <Button variant="outline" size="sm" onClick={refetch}>
              {t("common.tryAgain")}
            </Button>
          }
        />
      </div>
    )
  }

  const issued = (data ?? [])
    .filter((c): c is Certificate & { issued_at: string } => c.status === "approved" && !!c.issued_at)
    .sort((a, b) => a.issued_at.localeCompare(b.issued_at))
  const name = issued.find((c) => c.student_name)?.student_name ?? user?.full_name ?? "—"
  const today = formatDayLong(documentDay(null, new Date().toISOString()), undefined, DOCUMENT_LOCALE)
  // Each course on the school's day, as its certificate prints it.
  const issuedDay = (c: Certificate) => formatDayLong(documentDay(c.issued_on, c.issued_at), undefined, DOCUMENT_LOCALE)
  const title = (c: Certificate) => c.course_title ?? c.archived_course_title ?? "—"

  // One school: it heads the sheet. Several: each line names its own.
  const schools = [...new Set(issued.map((c) => c.school_name || "Equip"))]
  const oneSchool = schools.length === 1 ? schools[0] : null
  const oneCity = oneSchool ? (issued.find((c) => c.school_city)?.school_city ?? null) : null

  const rows = issued.map((c) => ({ cert: c, grade: transcriptGrade(c, t) }))
  const main = mainSymbolScheme(rows.map((r) => r.grade))
  // A grade in another scale than most of the sheet carries its scale's name.
  const scaleMark = (r: (typeof rows)[number]) =>
    r.grade.symbolScheme && r.grade.symbolScheme !== main ? schemeName(r.grade.symbolScheme, t) : null
  const anyMarked = rows.some((r) => scaleMark(r) !== null)
  // «Grades: letter scale A–F.» is a claim about every line, so it is made
  // only when every line is in that scale. Otherwise the marks speak.
  const allMain = rows.every((r) => r.grade.symbolScheme === main)

  const withHours = issued.some((c) => c.academic_hours)
  const totalHours =
    issued.length > 1 && issued.every((c) => c.academic_hours)
      ? issued.reduce((sum, c) => sum + (c.academic_hours ?? 0), 0)
      : null

  return (
    <div className="container mx-auto px-4 py-6 max-w-3xl">
      <div className="mb-4 flex items-center justify-between print:hidden">
        <Link to="/certificates">
          <Button variant="ghost" size="sm" className="-ml-2">
            <ArrowLeft className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
            {t("certificates.document.back")}
          </Button>
        </Link>
        <Button size="sm" onClick={() => window.print()} disabled={issued.length === 0}>
          <Printer className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
          {t("certificates.document.print")}
        </Button>
      </div>

      <article className="transcript-sheet rounded-md border border-edge bg-surface px-5 py-8 sm:p-12 print:border-0">
        <header className="text-center">
          <p className="text-xs uppercase tracking-[0.28em] text-ink-muted">{t("certificates.transcript.kind")}</p>
          <h1 className="mt-3 break-words font-serif text-3xl font-semibold">{name}</h1>
          {oneSchool && issued.length > 0 && (
            <p className="mt-2 font-serif text-base">
              {oneSchool}
              {oneCity && <span className="text-ink-muted"> · {oneCity}</span>}
            </p>
          )}
          <p className="mt-1 text-sm text-ink-muted">{t("certificates.transcript.asOf", { date: today })}</p>
        </header>

        {issued.length === 0 ? (
          <p className="mt-10 text-center text-sm text-ink-muted">{t("certificates.transcript.empty")}</p>
        ) : (
          <>
            {/* A phone gets one entry per course; five columns do not fit
                390px. The table stays for a wide screen and for paper. */}
            <ul className="mt-8 divide-y divide-edge border-y border-edge sm:hidden print:hidden">
              {rows.map((r) => {
                const c = r.cert
                const mark = scaleMark(r)
                return (
                  <li key={c.id} className="grid grid-cols-[1fr_auto] gap-x-4 py-4">
                    <div className="min-w-0">
                      <p className="break-words font-serif text-base font-medium leading-snug">{title(c)}</p>
                      {!oneSchool && <p className="mt-0.5 text-xs text-ink-muted">{c.school_name || "Equip"}</p>}
                      <p className="mt-1 text-sm text-ink-muted">
                        <span className="sr-only">{t("certificates.transcript.completed")}: </span>
                        {issuedDay(c)}
                        {c.academic_hours ? (
                          <>
                            <span aria-hidden> · </span>
                            <span className="whitespace-nowrap">
                              {c.academic_hours} {t("certificates.transcript.hours").toLowerCase()}
                            </span>
                          </>
                        ) : null}
                      </p>
                      <p className="mt-1 font-mono text-xs text-ink-muted">
                        <span className="sr-only">{t("certificates.transcript.number")} </span>
                        {c.certificate_number}
                      </p>
                    </div>
                    <div className="text-right">
                      <span className="sr-only">{t("certificates.transcript.grade")}: </span>
                      <p
                        className={
                          r.grade.text !== t("certificates.transcript.completedOnly")
                            ? "font-serif text-lg font-semibold leading-snug"
                            : "text-sm leading-snug text-ink-muted"
                        }
                      >
                        {r.grade.text}
                      </p>
                      {mark && <p className="text-xs text-ink-muted">{mark}</p>}
                      {c.with_honors && (
                        <p className="font-serif text-sm italic">{t("certificates.transcript.withHonors")}</p>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>

            <table className="mt-10 hidden w-full border-collapse text-left text-sm sm:table print:table">
              <thead>
                <tr className="border-b border-edge text-xs uppercase tracking-[0.14em] text-ink-muted">
                  <th className="py-2 pr-3 font-medium">{t("certificates.transcript.course")}</th>
                  <th className="py-2 pr-3 font-medium">{t("certificates.transcript.completed")}</th>
                  {withHours && <th className="py-2 pr-3 text-right font-medium">{t("certificates.transcript.hours")}</th>}
                  <th className="py-2 pr-3 font-medium">{t("certificates.transcript.grade")}</th>
                  <th className="py-2 font-medium">{t("certificates.transcript.number")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const c = r.cert
                  const mark = scaleMark(r)
                  return (
                    <tr key={c.id} className="border-b border-edge align-top">
                      <td className="py-2.5 pr-3">
                        <span className="font-medium">{title(c)}</span>
                        {!oneSchool && <span className="block text-xs text-ink-muted">{c.school_name || "Equip"}</span>}
                      </td>
                      <td className="whitespace-nowrap py-2.5 pr-3">{issuedDay(c)}</td>
                      {withHours && (
                        <td className="py-2.5 pr-3 text-right tabular-nums">{c.academic_hours ?? "—"}</td>
                      )}
                      <td className="py-2.5 pr-3">
                        <span className="font-semibold">{r.grade.text}</span>
                        {mark && <span className="block whitespace-nowrap text-xs text-ink-muted">{mark}</span>}
                        {c.with_honors && (
                          <span className="block font-serif italic">{t("certificates.transcript.withHonors")}</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap py-2.5 font-mono text-xs">{c.certificate_number}</td>
                    </tr>
                  )
                })}
              </tbody>
              {totalHours !== null && (
                <tfoot>
                  <tr className="text-sm">
                    <td className="py-2.5 pr-3 font-medium" colSpan={2}>
                      {t("certificates.transcript.total")}
                    </td>
                    <td className="py-2.5 pr-3 text-right font-medium tabular-nums">{totalHours}</td>
                    <td colSpan={2} />
                  </tr>
                </tfoot>
              )}
            </table>
            {totalHours !== null && (
              <p className="mt-3 text-right text-sm sm:hidden print:hidden">
                {t("certificates.transcript.total")}: {totalHours} {t("certificates.transcript.hours").toLowerCase()}
              </p>
            )}
          </>
        )}

        {issued.length > 0 && (
          <footer className="mt-10 space-y-1 text-center text-xs text-ink-muted">
            {main && anyMarked && (
              <p>{t("certificates.transcript.scaleNote", { scheme: schemeName(main, t) })}</p>
            )}
            {main && allMain && <p>{t("certificates.transcript.scaleNoteAll", { scheme: schemeName(main, t) })}</p>}
            <p>{t("certificates.transcript.verify", { count: issued.length })}</p>
          </footer>
        )}
      </article>
    </div>
  )
}
