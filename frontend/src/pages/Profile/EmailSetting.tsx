import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Mail } from "lucide-react"

import { Checkbox } from "@/components/ui/checkbox"
import { useAuth } from "@/context/useAuth"
import { toast } from "@/lib/toast"
import { usersService } from "@/services/users"
import type { MailKind } from "@/types"

/**
 * The kinds of course mail the platform sends today, each one a switch.
 *
 * The privacy policy promises that every kind of course mail can be turned
 * off here. A switch for a mail that is never sent would promise something
 * else, so only the kinds that exist are listed; a new kind adds a line.
 * Account mail — sign-in, password, invitations — has no switch: without it
 * an account cannot be used, and the hint says so.
 */
const SENT_TODAY: MailKind[] = ["certificate_decided"]

export function EmailSetting() {
  const { user, applyUser } = useAuth()
  const { t } = useTranslation()
  const [saving, setSaving] = useState<MailKind | null>(null)
  if (!user) return null
  const off = user.email_off ?? []

  const toggle = async (kind: MailKind, on: boolean) => {
    setSaving(kind)
    try {
      const saved = await usersService.setEmailKind(kind, on)
      applyUser({ id: user.id, email_off: saved })
    } catch {
      toast({ title: t("profile.updateFailed"), variant: "destructive" })
    } finally {
      setSaving(null)
    }
  }

  return (
    <div className="flex flex-wrap items-start justify-between gap-3 px-4 py-4">
      <div className="flex min-w-0 items-start gap-3">
        <Mail className="mt-0.5 h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
        <div className="min-w-0">
          <p className="text-sm font-medium">{t("profile.emails.label")}</p>
          <p className="text-xs text-ink-muted">{t("profile.emails.hint")}</p>
        </div>
      </div>
      <div className="flex w-full flex-col gap-2 sm:w-72">
        {SENT_TODAY.map((kind) => (
          <label key={kind} className="flex cursor-pointer items-center gap-2 text-sm">
            <Checkbox
              checked={!off.includes(kind)}
              disabled={saving !== null}
              onCheckedChange={(v) => void toggle(kind, v === true)}
            />
            {t(`profile.emails.kinds.${kind}`)}
          </label>
        ))}
      </div>
    </div>
  )
}
