import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"

import { useConfirm } from "@/components/ui/alert-dialog"
import { useAuth } from "@/context/useAuth"
import { getErrorCode, getErrorContext } from "@/lib/errorCode"
import { rememberSignOutReason } from "@/lib/signOutReason"
import { toast } from "@/lib/toast"
import { usersService } from "@/services/users"

/**
 * "Delete account", at the very foot of the profile — a quiet link, not a
 * red panel: it is there for the person who looks for it, and nobody else
 * should be invited to press it.
 *
 * One confirmation, in the words of what actually happens: the account is
 * closed and hidden, the school keeps the record of the studies, and
 * a link emailed to the address brings it back. No typed confirmation — nothing else in
 * the application asks for one, and the deletion is reversible.
 *
 * Afterwards the person is signed out and lands on the sign-in page with a
 * line saying it is done and how to undo it (`auth.notice.accountDeleted`).
 */
export function DeleteAccountSetting() {
  const { t } = useTranslation()
  const confirm = useConfirm()
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)

  const remove = async () => {
    const ok = await confirm({
      title: t("account.delete.confirmTitle"),
      description: t("account.delete.confirmBody"),
      bulletList: [
        t("account.delete.whatHappens.signedOut"),
        t("account.delete.whatHappens.hidden"),
        t("account.delete.whatHappens.kept"),
        t("account.delete.whatHappens.restore"),
      ],
      confirmLabel: t("account.delete.confirm"),
      tone: "destructive",
    })
    if (!ok) return
    setBusy(true)
    try {
      await usersService.deleteMyAccount()
    } catch (err) {
      setBusy(false)
      const code = getErrorCode(err)
      const reason = getErrorContext(err)?.reason
      if (code === "account.cannot_delete" && reason === "only_director") {
        toast({ title: t("account.delete.onlyDirector"), variant: "destructive" })
      } else if (code === "account.cannot_delete") {
        toast({ title: t("account.delete.platformStaff"), variant: "destructive" })
      } else {
        toast({ title: t("account.delete.failed"), variant: "destructive" })
      }
      return
    }
    rememberSignOutReason("account_deleted")
    await logout()
    navigate("/login", { replace: true })
  }

  return (
    <div className="flex justify-center">
      <button
        type="button"
        onClick={() => void remove()}
        disabled={busy}
        className="text-xs text-ink-muted underline-offset-4 transition-colors duration-fast hover:text-destructive-ink hover:underline disabled:opacity-50"
      >
        {t("account.delete.button")}
      </button>
    </div>
  )
}
