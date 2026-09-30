import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { Loader2, Mail, Phone } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useAuth } from "@/context/useAuth"
import { activeIntlTag } from "@/i18n/config"
import { countriesSorted } from "@/lib/countries"
import { toast } from "@/lib/toast"
import { usersService } from "@/services/users"
import type { User } from "@/types"

/** Radix Select cannot hold "" — this is "not given". */
const NONE = "__none__"

interface Form {
  birth_date: string
  country_code: string
  region: string
  city: string
  church: string
}

function formOf(user: User): Form {
  return {
    birth_date: user.birth_date ?? "",
    country_code: user.country_code ?? "",
    region: user.region ?? "",
    city: user.city ?? "",
    church: user.church ?? "",
  }
}

/** Today as the reader's calendar has it, for the date field's upper bound. */
function todayKey(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

/**
 * Optional things a person may say about themselves. Nothing here is needed
 * to study; every field can stay empty. The database checks the same limits
 * (`profiles_personal_text_lengths_check`, the birth-date trigger), so this
 * form is a convenience, not the guard.
 *
 * The phone is shown but cannot be edited: until a number can be verified,
 * the database refuses it from the browser, and a field that looked editable
 * would only produce an error.
 */
export function PersonalDetailsCard() {
  const { user, applyUser } = useAuth()
  const { t, i18n } = useTranslation()
  const locale = activeIntlTag(i18n.resolvedLanguage ?? i18n.language)
  const countries = useMemo(() => countriesSorted(locale), [locale])
  const [form, setForm] = useState<Form | null>(null)
  const [saving, setSaving] = useState(false)

  if (!user) return null
  const saved = formOf(user)
  const value = form ?? saved
  const dirty = JSON.stringify(value) !== JSON.stringify(saved)
  const patch = (next: Partial<Form>) => setForm({ ...value, ...next })

  const birthInvalid = !!value.birth_date && (value.birth_date < "1900-01-01" || value.birth_date > todayKey())

  const save = async () => {
    if (birthInvalid) return
    setSaving(true)
    const trimmed = (s: string) => s.trim() || null
    try {
      const profile = await usersService.updateProfile({
        birth_date: value.birth_date || null,
        country_code: value.country_code || null,
        region: trimmed(value.region),
        city: trimmed(value.city),
        church: trimmed(value.church),
      })
      applyUser({
        ...user,
        birth_date: profile.birth_date ?? null,
        country_code: profile.country_code ?? null,
        region: profile.region ?? null,
        city: profile.city ?? null,
        church: profile.church ?? null,
      })
      setForm(null)
      toast({ title: t("profile.personal.saved"), variant: "success" })
    } catch {
      toast({ title: t("profile.updateFailed"), variant: "destructive" })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader className="space-y-1">
        <CardTitle>{t("profile.personal.title")}</CardTitle>
        <CardDescription>{t("profile.personal.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="profile-birth-date">{t("profile.personal.birthDate")}</Label>
            <Input
              id="profile-birth-date"
              type="date"
              min="1900-01-01"
              max={todayKey()}
              value={value.birth_date}
              onChange={(e) => patch({ birth_date: e.target.value })}
              aria-invalid={birthInvalid || undefined}
            />
            {birthInvalid && <p className="text-xs text-destructive">{t("profile.personal.birthDateInvalid")}</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="profile-country">{t("profile.personal.country")}</Label>
            <Select
              value={value.country_code || NONE}
              onValueChange={(next) => patch({ country_code: next === NONE ? "" : next })}
            >
              <SelectTrigger id="profile-country" size="md" aria-label={t("profile.personal.country")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>{t("profile.personal.notGiven")}</SelectItem>
                {countries.map((c) => (
                  <SelectItem key={c.code} value={c.code}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="profile-region">{t("profile.personal.region")}</Label>
            <Input
              id="profile-region"
              value={value.region}
              maxLength={100}
              autoComplete="address-level1"
              onChange={(e) => patch({ region: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="profile-city">{t("profile.personal.city")}</Label>
            <Input
              id="profile-city"
              value={value.city}
              maxLength={100}
              autoComplete="address-level2"
              onChange={(e) => patch({ city: e.target.value })}
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="profile-church">{t("profile.personal.church")}</Label>
            <Input
              id="profile-church"
              value={value.church}
              maxLength={200}
              placeholder={t("profile.personal.churchPlaceholder")}
              onChange={(e) => patch({ church: e.target.value })}
            />
          </div>
        </div>

        <dl className="divide-y divide-border rounded-md border border-edge">
          <div className="flex items-start gap-3 px-4 py-3">
            <Mail className="mt-0.5 h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
            <div className="min-w-0">
              <dt className="text-xs text-ink-muted">{t("auth.email")}</dt>
              <dd className="truncate text-sm font-medium">{user.email}</dd>
            </div>
          </div>
          <div className="flex items-start gap-3 px-4 py-3">
            <Phone className="mt-2.5 h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
            <div className="min-w-0 flex-1 space-y-1">
              <dt>
                <Label htmlFor="profile-phone" className="text-xs font-normal text-ink-muted">
                  {t("profile.personal.phone")}
                </Label>
              </dt>
              <dd className="space-y-1">
                <Input id="profile-phone" type="tel" value={user.phone ?? ""} disabled placeholder="+1 555 000 0000" />
                <p className="text-xs text-ink-muted">{t("profile.personal.phoneSoon")}</p>
              </dd>
            </div>
          </div>
        </dl>

        <div className="flex items-center gap-2">
          <Button onClick={save} disabled={!dirty || saving || birthInvalid}>
            {saving && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />}
            {t("common.save")}
          </Button>
          {dirty && !saving && (
            <Button variant="ghost" onClick={() => setForm(null)}>
              {t("common.cancel")}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
