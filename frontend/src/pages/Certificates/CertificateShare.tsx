import { useTranslation } from "react-i18next"
import { Link2, Share2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { getDisplayTimeZone } from "@/i18n/timeZone"
import { toast } from "@/lib/toast"
import type { Certificate } from "@/types"
import { linkedInAddUrl, verifyUrl } from "./shareLinks"

/**
 * Share the certificate, and put it on LinkedIn.
 *
 * For a student serving in a church the certificate is a real document, and
 * the page that verifies it is the one a pastor or an employer should see —
 * so that is what both buttons hand over, never the private page. On a phone
 * "Share" is the system sheet (WhatsApp, Telegram, Viber); elsewhere it
 * copies the link.
 */
export function CertificateShare({ cert }: { cert: Certificate }) {
  const { t } = useTranslation()
  const origin = window.location.origin
  const url = verifyUrl(cert, origin)
  const title = cert.course_title ?? cert.archived_course_title ?? ""

  const share = async () => {
    if (typeof navigator.share === "function") {
      try {
        await navigator.share({ title, text: t("certificates.share.text", { course: title }), url })
        return
      } catch (e) {
        // Closing the sheet is not a failure.
        if ((e as DOMException)?.name === "AbortError") return
      }
    }
    try {
      await navigator.clipboard.writeText(url)
      toast({ title: t("certificates.share.copied") })
    } catch {
      toast({ title: t("certificates.share.copyFailed"), variant: "destructive" })
    }
  }

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => void share()}>
        <Share2 className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
        {t("certificates.share.share")}
      </Button>
      <Button size="sm" variant="outline" asChild>
        {/* «LinkedIn» on the button, the whole action for the ear: the
            long label wrapped the page's three buttons onto two rows. */}
        <a
          href={linkedInAddUrl(cert, origin, getDisplayTimeZone())}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={t("certificates.share.linkedIn")}
        >
          <Link2 className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
          {t("certificates.share.linkedInShort")}
        </a>
      </Button>
    </>
  )
}
