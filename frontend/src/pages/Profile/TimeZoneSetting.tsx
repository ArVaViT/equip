import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { Clock, Loader2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useAuth } from "@/context/useAuth"
import { activeIntlTag } from "@/i18n/config"
import {
  browserTimeZone,
  getDisplayTimeZone,
  supportedTimeZones,
  timeZoneOffsetMinutes,
  timeZoneOptionLabel,
} from "@/i18n/timeZone"
import { toast } from "@/lib/toast"
import { usersService } from "@/services/users"

/**
 * The zone this person reads times in. It follows the device until they pick
 * one here; after that nothing automatic changes it (`time_zone_source`
 * `chosen`). "Follow this device" hands it back to the browser.
 */
export function TimeZoneSetting() {
  const { user, applyUser } = useAuth()
  const { t, i18n } = useTranslation()
  const locale = activeIntlTag(i18n.resolvedLanguage ?? i18n.language)
  const [saving, setSaving] = useState(false)
  const current = getDisplayTimeZone()
  const device = browserTimeZone()
  const chosen = user?.time_zone_source === "chosen"

  const zones = useMemo(() => {
    const all = supportedTimeZones()
    // The engine lists canonical names ("Europe/Kiev"); the profile or the
    // device may use the current one ("Europe/Kyiv"). Always offer both.
    for (const z of [current, device]) if (!all.includes(z)) all.push(z)
    const now = new Date()
    // West to east, as a phone's own picker lists them: the neighbours of
    // the reader's clock sit next to it, whatever the city is called.
    return all
      .map((z) => ({ zone: z, offset: timeZoneOffsetMinutes(z, now), label: timeZoneOptionLabel(locale, z, now) }))
      .sort((a, b) => a.offset - b.offset || a.zone.localeCompare(b.zone))
  }, [current, device, locale])

  if (!user) return null

  const save = async (zone: string, source: "chosen" | "detected") => {
    setSaving(true)
    try {
      const profile = await usersService.updateProfile({ time_zone: zone, time_zone_source: source })
      applyUser({ id: user.id, time_zone: profile.time_zone ?? zone, time_zone_source: source })
      toast({ title: t("profile.timeZone.saved", { zone: zone.replace(/_/g, " ") }), variant: "success" })
    } catch {
      toast({ title: t("profile.updateFailed"), variant: "destructive" })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-4">
      <div className="flex min-w-0 items-center gap-3">
        <Clock className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
        <div className="min-w-0">
          <p className="text-sm font-medium">{t("profile.timeZone.label")}</p>
          <p className="text-xs text-ink-muted">
            {chosen ? t("profile.timeZone.chosenHint") : t("profile.timeZone.deviceHint")}
          </p>
        </div>
      </div>
      <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
        <Select value={current} onValueChange={(z) => void save(z, "chosen")} disabled={saving}>
          <SelectTrigger size="sm" className="w-full sm:w-72" aria-label={t("profile.timeZone.label")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {zones.map((z) => (
              <SelectItem key={z.zone} value={z.zone}>
                {z.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {chosen && current !== device && (
          <Button variant="ghost" size="sm" disabled={saving} onClick={() => void save(device, "detected")}>
            {saving && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" strokeWidth={1.75} aria-hidden />}
            {t("profile.timeZone.useDevice")}
          </Button>
        )}
      </div>
    </div>
  )
}
