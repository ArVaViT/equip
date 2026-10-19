import { useEffect, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { MailX } from "lucide-react"

import { isAxiosError } from "axios"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import PageSpinner from "@/components/ui/PageSpinner"
import { PageHeader } from "@/components/patterns"
import { getErrorDetail } from "@/lib/errorDetail"
import { toast } from "@/lib/toast"
import { emailService, type UnsubscribeState } from "@/services/email"

type View =
  | { state: "loading" }
  | { state: "invalid" }
  | { state: "unavailable" }
  | { state: "ask" | "done"; info: UnsubscribeState }

/**
 * Only the server's own «no» means the link is bad. A dropped connection or
 * a 500 used to be shown as «this link does not work» — a working link
 * declared broken, to somebody who then went looking for the setting.
 */
function linkRefused(err: unknown): boolean {
  const status = isAxiosError(err) ? err.response?.status : undefined
  return status === 400 || status === 404 || status === 410 || status === 422
}

/**
 * Where the link at the foot of a course mail lands.
 *
 * It asks before it acts. Mail scanners open every link in a message; a
 * page that unsubscribed on load would turn people's mail off for them. The
 * mail client's own "unsubscribe" button does not come here — it posts
 * straight to the API (RFC 8058).
 *
 * Public, and exempt from the first-run consent screen: the privacy policy
 * promises that every course mail can be stopped from its own link.
 */
export default function UnsubscribePage() {
  const { t } = useTranslation()
  const [params] = useSearchParams()
  const token = params.get("token") ?? ""
  const [view, setView] = useState<View>({ state: "loading" })
  const [busy, setBusy] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!token) {
      setView({ state: "invalid" })
      return
    }
    let cancelled = false
    setView({ state: "loading" })
    emailService
      .readUnsubscribe(token)
      .then((info) => !cancelled && setView({ state: info.off ? "done" : "ask", info }))
      .catch((err: unknown) => !cancelled && setView({ state: linkRefused(err) ? "invalid" : "unavailable" }))
    return () => {
      cancelled = true
    }
  }, [token, attempt])

  const confirm = async () => {
    setBusy(true)
    try {
      const info = await emailService.unsubscribe(token)
      setView({ state: "done", info })
    } catch (err) {
      // The button stays: a failed request is tried again, not declared a
      // broken link.
      if (linkRefused(err)) setView({ state: "invalid" })
      else toast({ title: getErrorDetail(err), variant: "destructive" })
    } finally {
      setBusy(false)
    }
  }

  if (view.state === "loading") return <PageSpinner />
  const kind = view.state === "invalid" || view.state === "unavailable" ? null : t(`profile.emails.kinds.${view.info.kind}`)

  return (
    <div className="container mx-auto max-w-2xl px-4 py-10">
      <PageHeader title={t("unsubscribe.title")} />
      <Card className="mt-6">
        <CardContent className="space-y-4 py-8 text-center">
          <MailX className="mx-auto h-8 w-8 text-ink-muted" strokeWidth={1.5} aria-hidden />
          {view.state === "invalid" && <p className="text-sm text-ink-muted">{t("unsubscribe.invalid")}</p>}
          {view.state === "unavailable" && (
            <>
              <p className="text-sm text-ink-muted" role="alert">
                {t("unsubscribe.unavailable")}
              </p>
              <Button variant="outline" onClick={() => setAttempt((n) => n + 1)}>
                {t("common.tryAgain")}
              </Button>
            </>
          )}
          {view.state === "ask" && (
            <>
              <p className="text-sm">{t("unsubscribe.ask", { kind })}</p>
              <Button onClick={() => void confirm()} disabled={busy}>
                {t("unsubscribe.button")}
              </Button>
            </>
          )}
          {view.state === "done" && (
            <>
              <p className="text-sm" role="status">
                {t("unsubscribe.done", { kind })}
              </p>
              <p className="text-xs text-ink-muted">{t("unsubscribe.again")}</p>
            </>
          )}
          <div>
            <Link to="/profile" className="text-sm text-brand underline-offset-4 hover:underline">
              {t("unsubscribe.toProfile")}
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
