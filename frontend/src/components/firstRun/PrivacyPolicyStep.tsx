import { useEffect, useId, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { legalService, type LegalDocumentSummary } from "@/services/legal"
import { DEFAULT_LOCALE, isSupportedLocale } from "@/i18n/config"
import { toast } from "@/lib/toast"

interface Props {
  onAccept: () => void
}

/**
 * First-run Step 1 — Privacy Policy gate.
 *
 * Editorial composition matching the rest of the onboarding voice:
 * thin sage rule → eyebrow → Literata serif title → warm paragraph →
 * three short bullets → checkbox → single primary CTA.
 *
 * No skip path. The user MUST accept before continuing — this is the
 * legal gate, not a settings screen. Closing the browser without
 * accepting leaves nothing persisted, so the gate fires again next
 * visit.
 *
 * What changed on 2026-08-13: this used to write a `localStorage` flag and
 * name two documents that did not exist, under a line promising the full
 * version was always available from the footer, where there was no link.
 * Both documents are real now, both are linked from this screen and from the
 * footer, and the acceptance goes to the server with the version and a hash
 * of the text — because proving that a person agreed, and to what, is the
 * entire job of a consent record.
 */
export function PrivacyPolicyStep({ onAccept }: Props) {
  const { i18n, t } = useTranslation()
  // The language the reader is actually in. It used to collapse to "ru" for
  // everyone but English readers, so a German student's consent record said
  // they had read the Russian policy — a claim the record exists to make
  // checkable, stated wrongly. The server records the language it served.
  const locale = isSupportedLocale(i18n.language) ? i18n.language : DEFAULT_LOCALE
  const [accepted, setAccepted] = useState(false)
  const [saving, setSaving] = useState(false)
  const [documents, setDocuments] = useState<LegalDocumentSummary[] | null>(null)
  const checkboxId = useId()

  useEffect(() => {
    let cancelled = false
    legalService.documents().then(
      (list) => {
        if (!cancelled) setDocuments(list)
      },
      () => {
        // Fetched again at click time. A network hiccup on mount must not
        // leave somebody staring at a permanently dead Continue button.
        if (!cancelled) setDocuments(null)
      },
    )
    return () => {
      cancelled = true
    }
  }, [])

  const confirm = async () => {
    setSaving(true)
    try {
      const list = documents ?? (await legalService.documents())
      // One tick, both documents — that is what the checkbox says, and
      // recording only one of them would make the record narrower than the
      // sentence the person actually agreed to. Accepting something already
      // accepted is idempotent on the server, so this is safe to repeat.
      for (const doc of list) {
        await legalService.accept(doc.slug, doc.version, locale)
      }
      onAccept()
    } catch {
      toast({ title: t("firstRun.privacy.saveFailed"), variant: "destructive" })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex w-full max-w-xl flex-col items-center gap-5 text-center">
      <span className="block h-px w-12 bg-accent/60" aria-hidden />
      <p className="text-xs font-medium uppercase tracking-[0.22em] text-accent">
        {t("firstRun.privacy.eyebrow")}
      </p>
      <h1 className="font-serif text-2xl font-semibold leading-tight tracking-tight text-ink sm:text-3xl">
        {t("firstRun.privacy.title")}
      </h1>
      <p className="max-w-md text-sm leading-relaxed text-ink-muted sm:text-base">
        {t("firstRun.privacy.intro")}
      </p>

      <ul className="mt-2 w-full space-y-3 text-left text-sm leading-relaxed text-ink-muted">
        <li className="flex gap-3 rounded-md bg-muted/20 p-3">
          <span aria-hidden className="mt-1.5 block h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
          <span>{t("firstRun.privacy.bullets.collect")}</span>
        </li>
        <li className="flex gap-3 rounded-md bg-muted/20 p-3">
          <span aria-hidden className="mt-1.5 block h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
          <span>{t("firstRun.privacy.bullets.share")}</span>
        </li>
        <li className="flex gap-3 rounded-md bg-muted/20 p-3">
          <span aria-hidden className="mt-1.5 block h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
          <span>{t("firstRun.privacy.bullets.control")}</span>
        </li>
      </ul>

      <div className="mt-2 flex w-full items-start gap-3 rounded-md bg-surface p-3 text-left">
        <Checkbox
          id={checkboxId}
          checked={accepted}
          onCheckedChange={(v) => setAccepted(v === true)}
          className="mt-0.5"
        />
        <label
          htmlFor={checkboxId}
          className="cursor-pointer text-sm leading-snug text-ink"
        >
          {t("firstRun.privacy.checkbox")}
        </label>
      </div>

      {/* The documents themselves, one click away and openable in a new tab.
          Asking somebody to accept a text they cannot reach is the thing this
          screen was doing wrong. */}
      <p className="text-sm text-ink-muted">
        <Link to="/privacy" target="_blank" className="text-brand underline-offset-4 hover:underline">
          {t("legal.privacy")}
        </Link>
        {" · "}
        <Link to="/terms" target="_blank" className="text-brand underline-offset-4 hover:underline">
          {t("legal.terms")}
        </Link>
      </p>

      <Button
        type="button"
        onClick={confirm}
        disabled={!accepted || saving}
        size="lg"
        className="w-full sm:w-auto sm:min-w-[160px]"
      >
        {saving && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />}
        {t("firstRun.privacy.next")}
      </Button>
    </div>
  )
}
