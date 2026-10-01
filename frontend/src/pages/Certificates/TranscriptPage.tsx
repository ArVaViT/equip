import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { ArrowLeft, Printer } from "lucide-react"

import { Button } from "@/components/ui/button"
import PageSpinner from "@/components/ui/PageSpinner"
import { ErrorState } from "@/components/patterns"
import { useAuth } from "@/context/useAuth"
import { useAsyncData } from "@/hooks/useAsyncData"
import { getDisplayTimeZone } from "@/i18n/timeZone"
import { getErrorDetail } from "@/lib/errorDetail"
import { coursesService } from "@/services/courses"
import type { Certificate } from "@/types"
import "./transcript-print.css"

/**
 * Every course a student has completed, on one sheet: what a pastor asks for
 * before an ordination, and a school before it accepts a transfer.
 *
 * Only certificates actually issued, oldest first, each with the number a
 * reader can check at /verify. English, like the certificate and the
 * ведомость: documents on this platform are English whatever the interface
 * language, so the strings carry the same English value in every catalogue.
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
  const date = (iso: string) =>
    new Date(iso).toLocaleDateString("en-GB", {
      day: "numeric",
      month: "long",
      year: "numeric",
      timeZone: getDisplayTimeZone(),
    })

  return (
    <div className="container mx-auto max-w-4xl px-4 py-6">
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

      <article className="transcript-sheet rounded-md border border-edge bg-surface p-8 sm:p-12">
        <header className="text-center">
          <p className="text-xs uppercase tracking-[0.28em] text-ink-muted">{t("certificates.transcript.kind")}</p>
          <h1 className="mt-3 font-serif text-3xl font-semibold">{name}</h1>
          <p className="mt-2 text-sm text-ink-muted">
            {t("certificates.transcript.asOf", { date: date(new Date().toISOString()) })}
          </p>
        </header>

        {issued.length === 0 ? (
          <p className="mt-10 text-center text-sm text-ink-muted">{t("certificates.transcript.empty")}</p>
        ) : (
          <table className="mt-10 w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-edge text-xs uppercase tracking-[0.14em] text-ink-muted">
                <th className="py-2 pr-3 font-medium">{t("certificates.transcript.course")}</th>
                <th className="py-2 pr-3 font-medium">{t("certificates.transcript.school")}</th>
                <th className="py-2 pr-3 font-medium">{t("certificates.transcript.completed")}</th>
                <th className="py-2 font-medium">{t("certificates.transcript.number")}</th>
              </tr>
            </thead>
            <tbody>
              {issued.map((c) => (
                <tr key={c.id} className="border-b border-edge align-top">
                  <td className="py-2.5 pr-3 font-medium">{c.course_title ?? c.archived_course_title ?? "—"}</td>
                  <td className="py-2.5 pr-3">{c.school_name ?? "Equip"}</td>
                  <td className="whitespace-nowrap py-2.5 pr-3">{date(c.issued_at)}</td>
                  <td className="whitespace-nowrap py-2.5 font-mono text-xs">{c.certificate_number}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <footer className="mt-10 text-center text-xs text-ink-muted">
          {t("certificates.transcript.verify", { count: issued.length })}
        </footer>
      </article>
    </div>
  )
}
