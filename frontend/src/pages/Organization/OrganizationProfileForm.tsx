import { useId, useState } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { getErrorDetail } from "@/lib/errorDetail"
import { toast } from "@/lib/toast"
import { organizationsService, type OrganizationPage } from "@/services/organizations"

/** Mirrors ``OrganizationProfileUpdate.description`` (≤280): a paragraph that fits a card. */
const DESCRIPTION_MAX = 280

/**
 * What the organization says about itself, written by its director on the
 * page itself — the paragraph, the website, whether to show how many
 * belong. The name and the address stay with the platform.
 */
export function OrganizationProfileForm({
  organizationId,
  page,
  onDone,
}: {
  organizationId: string
  page: OrganizationPage
  onDone: (changed: boolean) => void
}) {
  const { t } = useTranslation()
  const ids = useId()
  const [description, setDescription] = useState(page.description ?? "")
  const [website, setWebsite] = useState(page.website_url ?? "")
  const [showMembers, setShowMembers] = useState<boolean>(page.show_member_count ?? true)
  const [saving, setSaving] = useState(false)
  const websiteTyped = website.trim()
  const websiteBroken = websiteTyped !== "" && !/^https:\/\/\S+\.\S+/.test(websiteTyped)

  const save = async () => {
    setSaving(true)
    try {
      await organizationsService.updateProfile(organizationId, {
        description: description.trim() || null,
        website_url: websiteTyped || null,
        show_member_count: showMembers,
      })
      toast({ title: t("organization.form.saved"), variant: "success" })
      onDone(true)
    } catch (err) {
      toast({ title: getErrorDetail(err, t("organization.form.failed")), variant: "destructive" })
    } finally {
      setSaving(false)
    }
  }

  return (
    <form
      className="mt-6 max-w-prose space-y-4 rounded-card border border-edge bg-muted/30 p-5"
      onSubmit={(e) => {
        e.preventDefault()
        if (!websiteBroken) void save()
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor={`${ids}-description`}>{t("organization.form.description")}</Label>
        <Textarea
          id={`${ids}-description`}
          value={description}
          maxLength={DESCRIPTION_MAX}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={t("organization.form.descriptionPlaceholder")}
          aria-describedby={`${ids}-description-count`}
        />
        <p id={`${ids}-description-count`} className="text-right text-xs tabular-nums text-ink-muted">
          {description.length}/{DESCRIPTION_MAX}
        </p>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${ids}-website`}>{t("organization.form.website")}</Label>
        <Input
          id={`${ids}-website`}
          type="url"
          inputMode="url"
          value={website}
          onChange={(e) => setWebsite(e.target.value)}
          placeholder={t("organization.form.websitePlaceholder")}
          aria-invalid={websiteBroken || undefined}
          aria-describedby={`${ids}-website-hint`}
        />
        <p id={`${ids}-website-hint`} className={websiteBroken ? "text-xs text-destructive" : "text-xs text-ink-muted"}>
          {websiteBroken ? t("organization.form.websiteBroken") : t("organization.form.websiteHint")}
        </p>
      </div>
      <div className="flex items-start gap-2">
        <Checkbox
          id={`${ids}-members`}
          checked={showMembers}
          onCheckedChange={(v) => setShowMembers(v === true)}
        />
        <div>
          <Label htmlFor={`${ids}-members`} className="font-normal">
            {t("organization.form.showMembers")}
          </Label>
          <p className="text-xs text-ink-muted">{t("organization.form.showMembersHint")}</p>
        </div>
      </div>
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={saving || websiteBroken}>
          {saving ? t("organization.form.saving") : t("organization.form.save")}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => onDone(false)}>
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  )
}
