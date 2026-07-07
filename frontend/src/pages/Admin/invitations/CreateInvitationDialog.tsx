import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Modal } from "@/components/patterns"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { invitationsService } from "@/services/invitations"
import { toast } from "@/lib/toast"
import { getErrorDetail } from "@/lib/errorDetail"
import type { InvitationRole } from "@/types"

interface Props {
  open: boolean
  onClose: () => void
  onCreated: () => void
}

const EMAIL_MAX_LENGTH = 254

/** Invite-by-email form. Admin-only can invite the 'teacher' or
 *  'student' role -- 'admin' is deliberately not selectable, mirroring
 *  the backend schema Literal that makes admin un-invitable. */
export function CreateInvitationDialog({ open, onClose, onCreated }: Props) {
  const { t } = useTranslation()
  const [email, setEmail] = useState("")
  const [role, setRole] = useState<InvitationRole>("student")
  const [saving, setSaving] = useState(false)

  const reset = () => {
    setEmail("")
    setRole("student")
  }

  const handleClose = () => {
    if (saving) return
    reset()
    onClose()
  }

  const isValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())

  const submit = async () => {
    if (!isValid) return
    setSaving(true)
    try {
      await invitationsService.createInvitation(email.trim(), role)
      toast({ title: t("admin.invitations.toast.created"), variant: "success" })
      reset()
      onCreated()
    } catch (err) {
      toast({
        title: getErrorDetail(err, t("admin.invitations.toast.createFailed")),
        variant: "destructive",
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open={open} onClose={handleClose} title={t("admin.invitations.createTitle")}>
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label className="text-xs">{t("admin.invitations.fieldEmail")}</Label>
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value.slice(0, EMAIL_MAX_LENGTH))}
            maxLength={EMAIL_MAX_LENGTH}
            placeholder={t("admin.invitations.emailPlaceholder")}
            autoFocus
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">{t("admin.invitations.fieldRole")}</Label>
          <Select value={role} onValueChange={(v) => setRole(v as InvitationRole)}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="student">{t("roles.student")}</SelectItem>
              <SelectItem value="teacher">{t("roles.teacher")}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={handleClose} disabled={saving}>
            {t("common.cancel")}
          </Button>
          <Button onClick={submit} disabled={!isValid || saving}>
            {saving ? t("admin.invitations.sending") : t("admin.invitations.send")}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
