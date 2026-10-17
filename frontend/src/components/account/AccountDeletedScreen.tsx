import { useCallback, useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { MailCheck, UserX } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useAuth } from "@/context/useAuth"
import { useCooldown } from "@/hooks/useCooldown"
import { formatDateLong } from "@/i18n/format"
import {
  forgetRestoreRequested,
  publishAccountDeleted,
  rememberRestoreRequested,
  wasRestoreRequested,
} from "@/lib/accountDeleted"
import { emailSendErrorMessage } from "@/lib/authError"
import { takeReturnPath } from "@/lib/authRedirect"
import { getErrorCode } from "@/lib/errorCode"
import { toast } from "@/lib/toast"
import { authService } from "@/services/auth"
import { usersService } from "@/services/users"

// The send-email hook's window for a sign-in link:
// `supabase/functions/send-email/copy.ts::REPEAT_WINDOWS`.
const RESEND_COOLDOWN_SECONDS = 120

type Phase = "idle" | "sent"

/**
 * What a person sees when they sign in to an account they deleted.
 *
 * This is also where somebody lands who deleted their account and later
 * "signs up again" with the same address: Supabase never makes a second
 * account for an address it holds, so the sign-in reaches the old one, and
 * here it is. Nothing on this screen is shown to anybody who has not just
 * signed in, so it tells no stranger that the address was ever registered.
 *
 * Restoring is by the link we email to the account's address (Vadym,
 * 2026-10-17): a password or Google sign-in reaches this screen, and
 * "Restore" sends the link; the server refuses anything else with
 * `account.restore_needs_email_link`. Opening the link signs the person in
 * through the email, and then the same button restores at once — or by
 * itself, when the link was asked for in this browser.
 *
 * Opened on another device, the link restores the account there; this tab
 * notices when it comes back into focus (a restore of an account that is
 * already back answers 204).
 */
export function AccountDeletedScreen() {
  const { t } = useTranslation()
  const { user, logout, refreshUser } = useAuth()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [phase, setPhase] = useState<Phase>("idle")
  const [error, setError] = useState("")
  const { remaining, restart } = useCooldown(RESEND_COOLDOWN_SECONDS, false)
  const userId = user?.id
  const email = user?.email ?? ""

  const leave = async () => {
    if (userId) forgetRestoreRequested(userId)
    publishAccountDeleted(false)
    await logout()
    navigate("/login", { replace: true })
  }

  const sendLink = useCallback(async () => {
    if (!userId || !email) return
    setError("")
    try {
      await authService.sendSignInLink(email)
      rememberRestoreRequested(userId)
      setPhase("sent")
      restart()
    } catch (err) {
      // A refused repeat means the earlier email and its link still stand.
      setError(emailSendErrorMessage(err))
      setPhase("sent")
    }
  }, [email, restart, userId])

  /**
   * Try to restore. `quiet` is the automatic attempt (arrival from the link,
   * coming back to the tab): it never sends an email and never shows a
   * failure — only success changes anything.
   */
  const restore = useCallback(
    async (quiet: boolean) => {
      setBusy(true)
      try {
        await usersService.restoreMyAccount()
        if (userId) forgetRestoreRequested(userId)
        publishAccountDeleted(false)
        await refreshUser()
        toast({ title: t("account.deleted.restored"), variant: "success" })
        // Where the sign-in was heading — an invitation, a lesson — is still
        // remembered: this screen stood in front of it, nothing spent it.
        navigate(takeReturnPath() ?? "/", { replace: true })
      } catch (err) {
        if (quiet) return
        if (getErrorCode(err) === "account.restore_needs_email_link") {
          await sendLink()
          return
        }
        toast({ title: t("account.deleted.restoreFailed"), variant: "destructive" })
      } finally {
        setBusy(false)
      }
    },
    [navigate, refreshUser, sendLink, t, userId],
  )

  // Arriving here from the link asked for in this browser: finish the job.
  const tried = useRef(false)
  useEffect(() => {
    if (tried.current || !userId || !wasRestoreRequested(userId)) return
    tried.current = true
    setPhase("sent")
    void restore(true)
  }, [restore, userId])

  // The link opened on the phone restores the account there; this tab
  // finds out when the person comes back to it.
  useEffect(() => {
    if (phase !== "sent") return
    const onVisible = () => {
      if (document.visibilityState === "visible") void restore(true)
    }
    document.addEventListener("visibilitychange", onVisible)
    return () => document.removeEventListener("visibilitychange", onVisible)
  }, [phase, restore])

  const when = user?.deleted_at ? formatDateLong(user.deleted_at) : null

  return (
    <main id="main-content" className="container mx-auto flex min-h-screen max-w-lg items-center px-4 py-10">
      <Card className="w-full">
        <CardContent className="space-y-4 py-8 text-center">
          {phase === "sent" ? (
            <MailCheck className="mx-auto h-6 w-6 text-brand-ink" strokeWidth={1.75} aria-hidden />
          ) : (
            <UserX className="mx-auto h-6 w-6 text-ink-muted" strokeWidth={1.75} aria-hidden />
          )}
          <h1 className="text-lg font-semibold text-ink">{t("account.deleted.title")}</h1>
          {phase === "sent" ? (
            <p className="text-sm text-ink-muted" role="status">
              {error || t("account.deleted.linkSent", { email })}
            </p>
          ) : (
            <p className="text-sm text-ink-muted">
              {when ? t("account.deleted.bodyWithDate", { date: when }) : t("account.deleted.body")}
            </p>
          )}
          <div className="flex flex-col gap-2 pt-2 sm:flex-row sm:justify-center">
            {phase === "sent" ? (
              <Button variant="outline" onClick={() => void sendLink()} disabled={busy || remaining > 0}>
                {remaining > 0
                  ? t("auth.signInLinkAgainIn", { seconds: remaining })
                  : t("auth.signInLinkAgain")}
              </Button>
            ) : (
              <Button onClick={() => void restore(false)} disabled={busy}>
                {t("account.deleted.restore")}
              </Button>
            )}
            <Button variant="outline" onClick={() => void leave()} disabled={busy}>
              {t("common.signOut")}
            </Button>
          </div>
        </CardContent>
      </Card>
    </main>
  )
}
