import { useTranslation } from "react-i18next"
import { Link, useParams } from "react-router-dom"
import { ArrowLeft, Printer } from "lucide-react"
import { Button } from "@/components/ui/button"
import PageSpinner from "@/components/ui/PageSpinner"
import { coursesService } from "@/services/courses"
import { useAsyncData } from "@/hooks/useAsyncData"
import type { Certificate } from "@/types"
import "./certificate-print.css"

/**
 * The certificate, as a document rather than a row.
 *
 * Until now the platform issued a list item: an icon, a number, a status. What
 * a school gives someone is a sheet of paper with its name on it, and that
 * sheet is the only part of this product a stranger ever sees — an employer, a
 * pastor, a bishop. It is the artefact everything else exists to produce, and
 * it did not exist.
 *
 * Set as printed matter, so the composition is the design:
 *
 * - **A centred axis**, which is what a document of record uses and an app
 *   never does. The eye goes down the middle: institution → what this is →
 *   who → what they did.
 * - **One thing is large.** The student's name, in the serif, at 4xl. Everything
 *   else is furniture around it. A certificate where the course title competes
 *   with the person's name is a receipt.
 * - **Hairlines, not boxes.** A rule under the school and a rule above the
 *   signatures. Publications use rules where apps use cards, and this is a
 *   publication.
 * - **Small caps and wide tracking on the labels** — «certifies that», the
 *   signature captions — because that is how printed matter marks its
 *   furniture apart from its content.
 *
 * Everything on the face comes from the snapshot taken at issuance. A school
 * that renames itself does not rewrite what it already certified.
 *
 * English only, by decision: the ведомость and the certificate are documents,
 * and documents on this platform are English whatever the interface language.
 * The strings therefore carry the same English value in both catalogues —
 * putting that decision in the data rather than in a lint exception, where the
 * next person would not find it.
 */
export default function CertificateDocument() {
  const { certificateId } = useParams<{ certificateId: string }>()
  const { t } = useTranslation()
  const { data, loading } = useAsyncData(
    async () => (await coursesService.getMyCertificates()).find((c) => c.id === certificateId) ?? null,
    [certificateId],
  )

  if (loading) return <PageSpinner />
  const cert = data as Certificate | null
  if (!cert || cert.status !== "approved") {
    return (
      <div className="container mx-auto max-w-2xl px-4 py-16 text-center">
        <p className="text-ink-muted">{t("certificates.document.notIssued")}</p>
        <Link to="/certificates" className="mt-4 inline-block">
          <Button variant="outline" size="sm">{t("certificates.document.back")}</Button>
        </Link>
      </div>
    )
  }

  const issued = cert.issued_at ? new Date(cert.issued_at) : null
  const issuedLong = issued
    ? issued.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })
    : "—"

  return (
    <div className="container mx-auto max-w-4xl px-4 py-6">
      <div className="mb-4 flex items-center justify-between print:hidden">
        <Link to="/certificates">
          <Button variant="ghost" size="sm" className="-ml-2">
            <ArrowLeft className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
            {t("certificates.document.back")}
          </Button>
        </Link>
        <Button size="sm" onClick={() => window.print()}>
          <Printer className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
          {t("certificates.document.print")}
        </Button>
      </div>

      <article className="certificate-sheet">
        <header className="text-center">
          <h1 className="font-serif text-xl font-semibold tracking-[0.02em]">
            {cert.school_name ?? t("certificates.document.schoolUnnamed")}
          </h1>
          {cert.school_city && (
            <p className="mt-1 text-xs uppercase tracking-[0.22em] text-ink-muted">{cert.school_city}</p>
          )}
          <hr className="certificate-rule" />
        </header>

        <p className="mt-8 text-center text-xs uppercase tracking-[0.28em] text-ink-muted">
          {t("certificates.document.certificateOfCompletion")}
        </p>

        <p className="mt-10 text-center text-sm uppercase tracking-[0.2em] text-ink-muted">
          {t("certificates.document.certifies")}
        </p>
        {/* The one large thing on the page. */}
        <p className="mt-3 text-center font-serif text-4xl font-semibold">
          {cert.student_name ?? "—"}
        </p>

        <p className="mt-8 text-center text-sm uppercase tracking-[0.2em] text-ink-muted">
          {t("certificates.document.hasCompleted")}
        </p>
        <p className="mt-2 text-center font-serif text-2xl">
          {cert.course_title ?? cert.archived_course_title ?? "—"}
        </p>

        <p className="mt-10 text-center text-sm text-ink-muted">
          {t("certificates.document.issued", { date: issuedLong })}
        </p>

        <div className="certificate-signatures">
          <div>
            <div className="certificate-signature-line" />
            <p className="certificate-signature-caption">
              {cert.teacher_name ?? t("certificates.document.instructor")}
            </p>
            <p className="certificate-signature-role">{t("certificates.document.instructor")}</p>
          </div>
          <div>
            <div className="certificate-signature-line" />
            <p className="certificate-signature-caption">&nbsp;</p>
            <p className="certificate-signature-role">{t("certificates.document.director")}</p>
          </div>
        </div>

        <footer className="mt-10 text-center">
          {/* The number and where to check it. A certificate nobody can verify
              is a picture of a certificate. */}
          <p className="font-mono text-xs tracking-wide text-ink-muted">
            {cert.certificate_number}
          </p>
          <p className="mt-1 text-xs text-ink-muted">
            {t("certificates.document.verifyAt", { number: cert.certificate_number })}
          </p>
        </footer>
      </article>
    </div>
  )
}
