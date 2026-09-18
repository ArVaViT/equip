import { useId, useState } from "react"
import { useTranslation } from "react-i18next"
import { Modal } from "@/components/patterns"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
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
 *  the backend schema Literal that makes admin un-invitable.
 *
 *  The age statement is the second thing this form asks for and the reason
 *  it can no longer be one field and a button. Self-registration is from 16;
 *  an invitation is how somebody younger gets in, and from 2026-09-17 the
 *  floor under that is 13. Below it the platform does not want the account:
 *  a known under-13 turns COPPA on, which is verifiable parental consent, a
 *  records-access duty and a deletion duty, and there is no process here for
 *  any of them.
 *
 *  No date of birth is asked for. The sender knows the family; the platform
 *  does not, and collecting a child's birthday in order to protect children
 *  is a trade nobody wins. What is kept is the statement and who made it. */
export function CreateInvitationDialog({ open, onClose, onCreated }: Props) {
  const { t } = useTranslation()
  const [email, setEmail] = useState("")
  const [role, setRole] = useState<InvitationRole>("student")
  // Never pre-ticked, and reset on every close. A box that arrives already
  // ticked records agreement nobody gave — the same rule the consent gate
  // follows, and for the same reason.
  const [ageAttested, setAgeAttested] = useState(false)
  const [saving, setSaving] = useState(false)
  const ageCheckboxId = useId()

  const reset = () => {
    setEmail("")
    setRole("student")
    setAgeAttested(false)
  }

  const handleClose = () => {
    if (saving) return
    reset()
    onClose()
  }

  const emailLooksRight = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())
  const isValid = emailLooksRight && ageAttested

  const submit = async () => {
    if (!isValid) return
    setSaving(true)
    try {
      await invitationsService.createInvitation(email.trim(), role, ageAttested)
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
        {/* Directly above the button, with nothing between them: the
            statement being made is the last thing read before the click that
            makes it. */}
        <div className="flex w-full items-start gap-3 rounded-md bg-muted/20 p-3 text-left">
          <Checkbox
            id={ageCheckboxId}
            checked={ageAttested}
            onCheckedChange={(v) => setAgeAttested(v === true)}
            className="mt-0.5"
          />
          <label htmlFor={ageCheckboxId} className="cursor-pointer text-sm leading-snug text-ink">
            {t("admin.invitations.ageAttestation.label")}
            <span className="mt-1 block text-xs text-ink-muted">
              {t("admin.invitations.ageAttestation.help")}
            </span>
          </label>
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
