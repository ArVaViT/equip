import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Loader2, Save } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { adminService } from "@/services/admin"
import { getErrorDetail } from "@/lib/errorDetail"
import { toast } from "@/lib/toast"
import type { OrgSettings } from "@/types"

/**
 * What the school decides about itself.
 *
 * Every field here was read-only until now: putting a school's name on its own
 * ведомость meant somebody running an UPDATE against the production database.
 *
 * The band table is deliberately not editable from this screen. It is shared,
 * so changing it re-labels every live grade on the platform at once — the same
 * 84% that read «B» yesterday reads «A» today. That is a real thing a school
 * may want, and it is not a thing to offer beside a text box for the city. The
 * API takes it, validated and audited; a considered UI for it comes with the
 * transcript, where the consequences are visible on the same page.
 */
export function SchoolSettingsTab() {
  const { t } = useTranslation()
  const [settings, setSettings] = useState<OrgSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({ school_name_ru: "", school_name_en: "", city: "" })

  useEffect(() => {
    let cancelled = false
    adminService
      .getOrgSettings()
      .then((s) => {
        if (cancelled) return
        setSettings(s)
        setForm({
          school_name_ru: s.school_name_ru ?? "",
          school_name_en: s.school_name_en ?? "",
          city: s.city ?? "",
        })
      })
      .catch((err) => {
        if (!cancelled) toast({ title: getErrorDetail(err, t("admin.school.loadFailed")), variant: "destructive" })
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [t])

  const save = async () => {
    setSaving(true)
    try {
      // Empty means "not set", not an empty name on a document.
      const updated = await adminService.updateOrgSettings({
        school_name_ru: form.school_name_ru.trim() || null,
        school_name_en: form.school_name_en.trim() || null,
        city: form.city.trim() || null,
      })
      setSettings(updated)
      toast({ title: t("admin.school.saved"), variant: "success" })
    } catch (err) {
      toast({ title: getErrorDetail(err, t("admin.school.saveFailed")), variant: "destructive" })
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-8 text-sm text-ink-muted">
          <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />
          {t("common.loading")}
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-serif text-lg">{t("admin.school.title")}</CardTitle>
        <p className="text-sm text-ink-muted">{t("admin.school.description")}</p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <Label htmlFor="school-name-ru">{t("admin.school.nameRu")}</Label>
            <Input
              id="school-name-ru"
              value={form.school_name_ru}
              maxLength={200}
              onChange={(e) => setForm((f) => ({ ...f, school_name_ru: e.target.value }))}
            />
          </div>
          <div>
            <Label htmlFor="school-name-en">{t("admin.school.nameEn")}</Label>
            <Input
              id="school-name-en"
              value={form.school_name_en}
              maxLength={200}
              onChange={(e) => setForm((f) => ({ ...f, school_name_en: e.target.value }))}
            />
            {/* The ведомость is always in English, so this is the one that
                actually gets printed. Saying so beats a director discovering
                it from a signed document. */}
            <p className="mt-1 text-xs text-ink-muted">{t("admin.school.nameEnHint")}</p>
          </div>
        </div>
        <div className="sm:max-w-xs">
          <Label htmlFor="school-city">{t("admin.school.city")}</Label>
          <Input
            id="school-city"
            value={form.city}
            maxLength={120}
            onChange={(e) => setForm((f) => ({ ...f, city: e.target.value }))}
          />
        </div>

        <div className="rounded-lg border border-edge bg-muted/30 px-3 py-2.5 text-sm">
          <p className="font-medium">{t("admin.school.gradingTitle")}</p>
          <p className="mt-0.5 text-ink-muted">
            {t("admin.school.gradingSummary", {
              scheme: t(`gradingScheme.${settings?.default_grading_scheme}`, settings?.default_grading_scheme ?? ""),
              threshold: settings?.default_pass_threshold ?? "—",
            })}
          </p>
          {/* Changing the scale moves every live grade at once. It is not a
              thing to offer beside a text box for the city. */}
          <p className="mt-1 text-xs text-ink-muted">{t("admin.school.gradingNote")}</p>
        </div>

        <Button onClick={save} disabled={saving} size="sm">
          {saving ? (
            <Loader2 className="mr-1.5 h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />
          ) : (
            <Save className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
          )}
          {t("common.save")}
        </Button>
      </CardContent>
    </Card>
  )
}
