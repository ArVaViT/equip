import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { X } from "lucide-react"
import { legalService, type LegalDocumentSummary } from "@/services/legal"
import { useAuth } from "@/context/useAuth"

/** Where each document lives, so the banner can link to the thing it names. */
const PATHS: Record<string, string> = {
  privacy: "/privacy",
  terms: "/terms",
  "teacher-terms": "/teacher-terms",
}

/** The i18n key for each document's name. */
const NAMES: Record<string, string> = {
  privacy: "legal.privacy",
  terms: "legal.terms",
  "teacher-terms": "legal.teacherTerms",
}

/**
 * The other half of the promise the documents make about changes.
 *
 * A material change asks for a signature and gets a blocking gate. Everything
 * else — a correction, a plainer sentence, a shortened retention window, a
 * right added — is published and **announced**, and this is the announcement.
 * It is a strip, not a modal, because nothing is being asked: the reader is
 * being told, and telling somebody does not require taking the screen away
 * from them.
 *
 * Which changes land here rather than in the gate is decided by
 * ``Revision.consent`` in ``backend/app/legal/registry.py``, and what counts
 * as material is written out in each document's own "Changes" section. The
 * point of the whole arrangement is that a typo can be fixed. Under the
 * previous one the only lever was a version bump, which meant every account
 * met a consent screen over a comma — and a consent screen people meet over
 * commas is a consent screen people stop reading.
 *
 * Dismissal is recorded on the server rather than in ``localStorage``, so a
 * banner closed on a phone is not waiting on the laptop.
 */
export function LegalNoticeBanner() {
  const { user } = useAuth()
  const { t } = useTranslation()
  const [notices, setNotices] = useState<LegalDocumentSummary[]>([])

  useEffect(() => {
    if (!user?.id) {
      setNotices([])
      return
    }
    let cancelled = false
    legalService.status().then(
      (status) => {
        if (!cancelled) setNotices(status.notices)
      },
      () => {
        // Nothing to say and nothing to recover: a notice that fails to load
        // is shown on the next page load instead.
      },
    )
    return () => {
      cancelled = true
    }
  }, [user?.id])

  const notice = notices[0]
  if (!notice) return null

  const dismiss = () => {
    setNotices((rest) => rest.slice(1))
    // Fire-and-forget: if this does not land the banner comes back, which is
    // the harmless direction. Blocking the dismissal on a round trip would
    // make "close this" feel broken on a slow connection.
    void legalService.markNoticeSeen(notice.slug, notice.version).catch(() => {})
  }

  const path = PATHS[notice.slug] ?? "/terms"
  const name = t(NAMES[notice.slug] ?? "legal.terms")

  return (
    <div
      role="status"
      className="flex items-start gap-3 border-b border-edge bg-muted/30 px-4 py-2.5 text-sm text-ink-muted sm:px-6"
    >
      <p className="flex-1">
        {t("legalGate.notice.body", { document: name, date: notice.effective })}{" "}
        <Link to={path} className="text-brand underline-offset-4 hover:underline">
          {t("legalGate.notice.read")}
        </Link>
      </p>
      <button
        type="button"
        onClick={dismiss}
        aria-label={t("legalGate.notice.dismiss")}
        className="shrink-0 rounded-md p-1 text-ink-muted transition-colors hover:text-ink"
      >
        <X className="h-4 w-4" strokeWidth={1.75} aria-hidden />
      </button>
    </div>
  )
}
