import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link, useParams } from "react-router-dom"
import { ArrowLeft } from "lucide-react"
import { legalService, type LegalDocument } from "@/services/legal"
import { DEFAULT_LOCALE, isSupportedLocale } from "@/i18n/config"
import { renderLegalMarkdown } from "@/components/legal/renderLegalMarkdown"
import PageSpinner from "@/components/ui/PageSpinner"

export type LegalSlug = "privacy" | "terms"

/**
 * The page the consent checkbox has been pointing at all along.
 *
 * Public, because a person deciding whether to sign up has to be able to read
 * what they would be agreeing to — a policy you can only see after accepting
 * it is not a policy.
 *
 * Set as a document rather than as an app screen: the reading measure, the
 * serif, one column, no card. It is the same register as the certificate, and
 * for the same reason — these are the two artefacts here that are meant to be
 * read by somebody who does not otherwise use this product.
 */
export default function LegalDocumentPage({ slug }: { slug?: LegalSlug }) {
  const params = useParams<{ slug?: string }>()
  const resolved = (slug ?? params.slug ?? "privacy") as LegalSlug
  const { i18n, t } = useTranslation()
  // The reader's own language, whole. Collapsing everything that is not
  // English to Russian handed a German or Ukrainian reader the Russian
  // privacy policy — a text they cannot read, presented as the thing they
  // are agreeing to. The server answers in their language where these
  // documents exist in it and in English where they do not, and says which
  // one it sent.
  const locale = isSupportedLocale(i18n.language) ? i18n.language : DEFAULT_LOCALE
  const [doc, setDoc] = useState<LegalDocument | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    setDoc(null)
    setFailed(false)
    legalService
      .document(resolved, locale)
      .then((d) => {
        if (!cancelled) setDoc(d)
      })
      .catch(() => {
        // Not silent: a legal page that renders empty on a failed fetch reads
        // as "there is no policy", which is exactly the state we came from.
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [resolved, locale])

  return (
    <div className="mx-auto w-full max-w-[680px] px-4 py-10 sm:px-6 sm:py-16">
      <Link
        to="/"
        className="inline-flex items-center gap-1.5 text-sm text-ink-muted transition-colors hover:text-ink"
      >
        <ArrowLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden />
        {t("common.appName")}
      </Link>

      {failed && (
        <p className="mt-10 text-sm text-destructive" role="alert">
          {t("legal.loadFailed")}
        </p>
      )}
      {!doc && !failed && <PageSpinner variant="section" />}
      {doc && (
        <article className="mt-8">
          {doc.locale !== locale && (
            // Said plainly, in their language: the alternative is a reader
            // who thinks the English text in front of them is a rendering
            // fault rather than the document itself.
            <p className="mb-8 border-l-2 border-edge pl-4 text-sm text-ink-muted">{t("legal.englishOnly")}</p>
          )}
          {renderLegalMarkdown(doc.body)}
          {/* The fingerprint is on the page on purpose. It is what an
              acceptance record points at, and printing it means a person can
              check that the text they are reading is the text they agreed to. */}
          <p className="mt-12 border-t border-edge pt-4 font-mono text-xs text-ink-muted">
            {t("legal.fingerprint", { version: doc.version, sha: doc.sha256.slice(0, 16) })}
          </p>
        </article>
      )}
    </div>
  )
}
