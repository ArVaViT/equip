import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { UserX } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useAuth } from "@/context/useAuth"
import { formatDateLong } from "@/i18n/format"
import { publishAccountDeleted } from "@/lib/accountDeleted"
import { getErrorCode } from "@/lib/errorCode"
import { rememberSignOutReason } from "@/lib/signOutReason"
import { toast } from "@/lib/toast"
import { usersService } from "@/services/users"

/**
 * What a person sees when they sign in to an account they deleted.
 *
 * This is also where somebody lands who deleted their account and later
 * "signs up again" with the same address: Supabase never makes a second
 * account for an address it holds, so the sign-in — a password, a link, or
 * Google — reaches the old one, and here it is. Nothing on this screen is
 * shown to anybody who has not just proved the address, so it tells no
 * stranger that the address was ever registered.
 *
 * Two ways out and nothing else: restore it, exactly as it was, or leave
 * it deleted and sign out. A session older than the deletion cannot restore
 * (the server answers `account.restore_needs_sign_in`): it is signed out and
 * asked to sign in again, which is the proof.
 */
export function AccountDeletedScreen() {
  const { t } = useTranslation()
  const { user, logout, refreshUser } = useAuth()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)

  const leave = async (reason?: "restore_needs_sign_in") => {
    if (reason) rememberSignOutReason(reason)
    publishAccountDeleted(false)
    await logout()
    navigate("/login", { replace: true })
  }

  const restore = async () => {
    setBusy(true)
    try {
      await usersService.restoreMyAccount()
      publishAccountDeleted(false)
      await refreshUser()
      toast({ title: t("account.deleted.restored"), variant: "success" })
      navigate("/", { replace: true })
    } catch (err) {
      if (getErrorCode(err) === "account.restore_needs_sign_in") {
        await leave("restore_needs_sign_in")
        return
      }
      toast({ title: t("account.deleted.restoreFailed"), variant: "destructive" })
    } finally {
      setBusy(false)
    }
  }

  const when = user?.deleted_at ? formatDateLong(user.deleted_at) : null

  return (
    <main id="main-content" className="container mx-auto flex min-h-screen max-w-lg items-center px-4 py-10">
      <Card className="w-full">
        <CardContent className="space-y-4 py-8 text-center">
          <UserX className="mx-auto h-6 w-6 text-ink-muted" strokeWidth={1.75} aria-hidden />
          <h1 className="text-lg font-semibold text-ink">{t("account.deleted.title")}</h1>
          <p className="text-sm text-ink-muted">
            {when ? t("account.deleted.bodyWithDate", { date: when }) : t("account.deleted.body")}
          </p>
          <div className="flex flex-col gap-2 pt-2 sm:flex-row sm:justify-center">
            <Button onClick={() => void restore()} disabled={busy}>
              {t("account.deleted.restore")}
            </Button>
            <Button variant="outline" onClick={() => void leave()} disabled={busy}>
              {t("common.signOut")}
            </Button>
          </div>
        </CardContent>
      </Card>
    </main>
  )
}
