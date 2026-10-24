import { useId, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Camera, Loader2, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { getErrorDetail } from "@/lib/errorDetail"
import { toProxyImage } from "@/lib/images"
import { organizationInitials } from "@/lib/organizationInitials"
import { toast } from "@/lib/toast"
import { ORGANIZATION_LOGOS, acceptAttribute } from "@/lib/uploadLimits"
import { organizationsService, type OrganizationPage } from "@/services/organizations"
import { storageService } from "@/services/storage"

/** Mirrors ``OrganizationProfileUpdate.description`` (≤280): a paragraph that fits a card. */
const DESCRIPTION_MAX = 280

/**
 * What the organization says about itself, written by its director on the
 * page itself — the logo, the paragraph, the website, whether to show how
 * many belong. The name and the address stay with the platform.
 *
 * The logo is written the moment it is picked, the way a profile photo is
 * (`ProfilePage.handleAvatarChange`): a fresh key in the organization's own
 * folder, the page updated, then the previous file removed. The rest of
 * the form is written on save.
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
  const fileRef = useRef<HTMLInputElement>(null)
  const [description, setDescription] = useState(page.description ?? "")
  const [website, setWebsite] = useState(page.website_url ?? "")
  const [showMembers, setShowMembers] = useState<boolean>(page.show_member_count ?? true)
  const [saving, setSaving] = useState(false)
  const [logo, setLogo] = useState<string | null>(page.logo_url)
  const [logoBusy, setLogoBusy] = useState(false)
  // Already on the server when the form is cancelled: the page re-reads
  // itself all the same, so the header shows what the director just did.
  const [logoChanged, setLogoChanged] = useState(false)
  const websiteTyped = website.trim()
  const websiteBroken = websiteTyped !== "" && !/^https:\/\/\S+\.\S+/.test(websiteTyped)
  const logoSrc = toProxyImage(logo)

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

  const changeLogo = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setLogoBusy(true)
    try {
      if (file.size > ORGANIZATION_LOGOS.maxBytes) {
        toast({ title: t("profile.imageTooLarge"), variant: "destructive" })
        return
      }
      const previous = logo
      const url = await storageService.uploadOrganizationLogo(organizationId, file)
      await organizationsService.updateProfile(organizationId, { logo_url: url })
      setLogo(url)
      setLogoChanged(true)
      // After the page holds the new URL, never before. Best-effort: an
      // orphaned file in the bucket beats an error on an upload that worked.
      if (previous && previous !== url) {
        void storageService.removePublicObject(previous).catch(() => {})
      }
    } catch (err) {
      toast({ title: getErrorDetail(err, t("organization.form.failed")), variant: "destructive" })
    } finally {
      setLogoBusy(false)
      if (fileRef.current) fileRef.current.value = ""
    }
  }

  const removeLogo = async () => {
    const previous = logo
    if (!previous) return
    setLogoBusy(true)
    try {
      await organizationsService.updateProfile(organizationId, { logo_url: null })
      setLogo(null)
      setLogoChanged(true)
      void storageService.removePublicObject(previous).catch(() => {})
    } catch (err) {
      toast({ title: getErrorDetail(err, t("organization.form.failed")), variant: "destructive" })
    } finally {
      setLogoBusy(false)
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
        <Label htmlFor={`${ids}-logo`}>{t("organization.form.logo")}</Label>
        <div className="flex items-center gap-3">
          {logoSrc ? (
            <img src={logoSrc} alt="" className="h-14 w-14 shrink-0 rounded-lg border border-edge bg-surface object-contain" />
          ) : (
            // The same stand-in the page shows: the name's initials.
            <div
              aria-hidden
              className="flex h-14 w-14 shrink-0 items-center justify-center rounded-lg border border-edge bg-muted/40 font-serif text-xl font-semibold text-ink-muted"
            >
              {organizationInitials(page.public_name)}
            </div>
          )}
          <Button
            type="button"
            variant="outline"
            size="icon"
            disabled={logoBusy}
            onClick={() => fileRef.current?.click()}
            aria-label={t("organization.form.changeLogo")}
          >
            {logoBusy ? (
              <Loader2 className="h-5 w-5 animate-spin" strokeWidth={1.75} aria-hidden />
            ) : (
              <Camera className="h-5 w-5" strokeWidth={1.75} aria-hidden />
            )}
          </Button>
          {logo && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              disabled={logoBusy}
              onClick={() => void removeLogo()}
              aria-label={t("organization.form.removeLogo")}
            >
              <Trash2 className="h-5 w-5" strokeWidth={1.75} aria-hidden />
            </Button>
          )}
          <input
            ref={fileRef}
            id={`${ids}-logo`}
            type="file"
            accept={acceptAttribute(ORGANIZATION_LOGOS)}
            className="hidden"
            onChange={(e) => void changeLogo(e)}
          />
        </div>
      </div>
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
        <Button type="button" variant="ghost" size="sm" onClick={() => onDone(logoChanged)}>
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  )
}
