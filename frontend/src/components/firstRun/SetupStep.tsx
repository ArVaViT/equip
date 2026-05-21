import { useId, useRef, useState } from "react"
import type { Theme } from "@/context/theme-context"
import { useTranslation } from "react-i18next"
import { Camera, Loader2, Moon, Sun, User as UserIcon } from "lucide-react"
import i18n, { type SupportedLocale } from "@/i18n/config"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAuth } from "@/context/useAuth"
import { useTheme } from "@/context/useTheme"
import { usersService } from "@/services/users"
import { storageService } from "@/services/storage"
import { preferencesService } from "@/services/preferences"
import { toProxyImage } from "@/lib/images"
import { toast } from "@/lib/toast"
import { cn } from "@/lib/utils"

interface Props {
  /** Fires after the user clicks the primary CTA — whether saves
   *  succeeded or partially failed. The first-run gate must close
   *  either way; the orchestrator handles persistence of the
   *  completion flag. */
  onComplete: () => void
  /** Fires when the user clicks "Skip for now" — bypasses every
   *  save attempt, just closes the flow. */
  onSkip: () => void
}

/**
 * First-run Step 2 — Quick Setup.
 *
 * Pre-fills with the current profile so the user can confirm-by-
 * default or change one or two things. Avatar upload, name, theme,
 * and language are all editable here. Email is shown read-only with
 * a hint pointing at the profile page for changes (Supabase auth
 * requires a verification flow we don't want to inline here).
 *
 * Every save is best-effort: failures fall back gracefully (toast +
 * a final "couldn't save everything" notice in the orchestrator),
 * because the gate has to close so the user can use the app. The
 * profile page is available afterwards to retry.
 */
export function SetupStep({ onComplete, onSkip }: Props) {
  const { t } = useTranslation()
  const { user, refreshUser } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const fileRef = useRef<HTMLInputElement>(null)

  const nameId = useId()
  const emailId = useId()

  const [name, setName] = useState(user?.full_name ?? "")
  const [avatarUrl, setAvatarUrl] = useState(user?.avatar_url ?? null)
  // Snapshots of locale + theme at mount so a "Skip" can undo any
  // preview-clicks the user made. The theme and locale APIs apply
  // changes immediately so the user can see the preview; if they
  // skip without committing, the snapshots restore the prior state.
  const initialLocale: SupportedLocale =
    (user?.preferred_locale as SupportedLocale | undefined) ??
    (i18n.resolvedLanguage as SupportedLocale | undefined) ??
    "en"
  const initialThemeRef = useRef<Theme>(theme)
  const [locale, setLocale] = useState<SupportedLocale>(initialLocale)
  const [uploading, setUploading] = useState(false)
  const [saving, setSaving] = useState(false)

  const isBusy = saving || uploading

  const initials = (user?.full_name ?? user?.email ?? "")
    .split(/[\s@]/)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase())
    .join("")

  const handleAvatarChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !user) return
    if (file.size > 2 * 1024 * 1024) {
      toast({ title: t("firstRun.setup.avatar.tooBig"), variant: "destructive" })
      if (fileRef.current) fileRef.current.value = ""
      return
    }
    setUploading(true)
    try {
      const url = await storageService.uploadAvatar(user.id, file)
      await usersService.updateProfile({ avatar_url: url })
      setAvatarUrl(url)
      await refreshUser()
    } catch {
      toast({ title: t("firstRun.setup.saveFailed"), variant: "destructive" })
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ""
    }
  }

  // Locale clicks change the i18n bundle immediately so the user
  // can preview the result without saving — same pattern as the
  // theme toggle below. The server-side persist happens on submit.
  const handleLocaleChange = (next: SupportedLocale) => {
    setLocale(next)
    void i18n.changeLanguage(next)
  }

  const handleSubmit = async () => {
    if (!user) {
      onComplete()
      return
    }
    setSaving(true)
    // Snapshot for accurate failure-rollback. We previously SKIPPED
    // the PATCH when the value matched the snapshot — that turned out
    // to silently lose changes the user thought they had made (e.g.
    // re-typing the same name they see pre-filled, or confirming a
    // locale that another effect had already PATCHed away). The fix
    // is to always send the user's CURRENT chosen values on submit;
    // the backend is idempotent and the extra PATCH costs nothing.
    const initialFullName = user.full_name ?? ""
    const initialServerLocale = user.preferred_locale
    let nameFailed = false
    let localeFailed = false
    try {
      const trimmed = name.trim()
      if (trimmed) {
        await usersService.updateProfile({ full_name: trimmed })
      }
    } catch {
      nameFailed = true
    }
    try {
      await preferencesService.setPreferredLocale(locale)
    } catch {
      localeFailed = true
      // Roll the live i18n bundle back to whatever the server
      // actually has so the user doesn't see a language they
      // didn't manage to save. ``initialServerLocale`` is the
      // pre-submit truth.
      void i18n.changeLanguage(initialServerLocale)
    }
    try {
      await refreshUser()
    } catch {
      /* ignore — auth refresh failure is non-fatal here */
    }
    if (nameFailed || localeFailed) {
      toast({ title: t("firstRun.setup.saveFailed"), variant: "destructive" })
    } else {
      const nameChanged = name.trim() && name.trim() !== initialFullName
      const localeChanged = locale !== initialServerLocale
      if (nameChanged || localeChanged) {
        toast({ title: t("firstRun.setup.saveSuccess"), variant: "success" })
      }
    }
    setSaving(false)
    onComplete()
  }

  const handleSkip = () => {
    // Undo any preview-only changes the user made but didn't commit:
    // locale via i18n (theme was persisted immediately by the
    // ThemeProvider, so we reverse it here too if it drifted).
    if (i18n.resolvedLanguage !== initialLocale) {
      void i18n.changeLanguage(initialLocale)
    }
    if (theme !== initialThemeRef.current) {
      toggleTheme()
    }
    onSkip()
  }

  return (
    <div className="flex w-full max-w-xl flex-col items-center gap-5 text-center">
      <span className="block h-px w-12 bg-accent/60" aria-hidden />
      <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-accent">
        {t("firstRun.setup.eyebrow")}
      </p>
      <h1 className="font-serif text-2xl font-semibold leading-tight tracking-tight text-foreground sm:text-3xl">
        {t("firstRun.setup.title")}
      </h1>
      <p className="max-w-md text-sm leading-relaxed text-muted-foreground sm:text-base">
        {t("firstRun.setup.intro")}
      </p>

      <div className="mt-2 flex w-full flex-col gap-5 text-left">
        {/* Avatar row */}
        <div className="flex items-center gap-4">
          <div className="relative shrink-0">
            {avatarUrl ? (
              <img
                src={toProxyImage(avatarUrl)}
                alt=""
                className="h-16 w-16 rounded-full border border-border object-cover"
              />
            ) : (
              <div className="flex h-16 w-16 items-center justify-center rounded-full border border-border bg-muted font-serif text-base font-semibold text-foreground">
                {initials || (
                  <UserIcon className="h-7 w-7 text-muted-foreground" strokeWidth={1.75} aria-hidden />
                )}
              </div>
            )}
          </div>
          <div className="flex-1">
            <Label className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
              {t("firstRun.setup.avatar.label")}
            </Label>
            <div className="mt-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => fileRef.current?.click()}
                disabled={isBusy}
              >
                {uploading ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />
                ) : (
                  <Camera className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.75} />
                )}
                {t("firstRun.setup.avatar.change")}
              </Button>
              <input
                ref={fileRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/gif"
                className="hidden"
                disabled={isBusy}
                onChange={handleAvatarChange}
              />
            </div>
          </div>
        </div>

        {/* Name */}
        <div>
          <Label
            htmlFor={nameId}
            className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground"
          >
            {t("firstRun.setup.name.label")}
          </Label>
          <Input
            id={nameId}
            value={name}
            onChange={(e) => setName(e.target.value.slice(0, 100))}
            placeholder={t("firstRun.setup.name.placeholder")}
            maxLength={100}
            className="mt-2"
          />
        </div>

        {/* Email (read-only) */}
        <div>
          <Label
            htmlFor={emailId}
            className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground"
          >
            {t("firstRun.setup.email.label")}
          </Label>
          <Input
            id={emailId}
            value={user?.email ?? ""}
            readOnly
            // Skipped by the focus trap — typing is impossible, so
            // landing a Tab cursor here just confuses keyboard users.
            tabIndex={-1}
            className="mt-2 cursor-not-allowed bg-muted/40 text-muted-foreground"
          />
          <p className="mt-1.5 text-xs text-muted-foreground/80">
            {t("firstRun.setup.email.hint")}
          </p>
        </div>

        {/* Theme — visual toggle, preview-on-click via the live
            useTheme hook (same context that powers the header toggle). */}
        <div>
          <Label className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            {t("firstRun.setup.theme.label")}
          </Label>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => theme !== "light" && toggleTheme()}
              aria-pressed={theme === "light"}
              className={cn(
                "flex items-center gap-2 rounded-md border p-3 text-sm transition-colors",
                theme === "light"
                  ? "border-primary bg-primary/[0.04] ring-1 ring-primary/40 text-foreground"
                  : "border-border text-muted-foreground hover:border-primary/30 hover:bg-muted/40",
              )}
            >
              <Sun className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden />
              {t("firstRun.setup.theme.light")}
            </button>
            <button
              type="button"
              onClick={() => theme !== "dark" && toggleTheme()}
              aria-pressed={theme === "dark"}
              className={cn(
                "flex items-center gap-2 rounded-md border p-3 text-sm transition-colors",
                theme === "dark"
                  ? "border-primary bg-primary/[0.04] ring-1 ring-primary/40 text-foreground"
                  : "border-border text-muted-foreground hover:border-primary/30 hover:bg-muted/40",
              )}
            >
              <Moon className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden />
              {t("firstRun.setup.theme.dark")}
            </button>
          </div>
        </div>

        {/* Language — same preview pattern */}
        <div>
          <Label className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            {t("firstRun.setup.language.label")}
          </Label>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => handleLocaleChange("en")}
              aria-pressed={locale === "en"}
              className={cn(
                "rounded-md border p-3 text-sm transition-colors",
                locale === "en"
                  ? "border-primary bg-primary/[0.04] ring-1 ring-primary/40 text-foreground"
                  : "border-border text-muted-foreground hover:border-primary/30 hover:bg-muted/40",
              )}
            >
              {t("firstRun.setup.language.en")}
            </button>
            <button
              type="button"
              onClick={() => handleLocaleChange("ru")}
              aria-pressed={locale === "ru"}
              className={cn(
                "rounded-md border p-3 text-sm transition-colors",
                locale === "ru"
                  ? "border-primary bg-primary/[0.04] ring-1 ring-primary/40 text-foreground"
                  : "border-border text-muted-foreground hover:border-primary/30 hover:bg-muted/40",
              )}
            >
              {t("firstRun.setup.language.ru")}
            </button>
          </div>
        </div>
      </div>

      <div className="mt-2 flex w-full flex-col items-center gap-2 sm:flex-row sm:justify-center">
        <Button
          type="button"
          onClick={handleSubmit}
          disabled={isBusy}
          size="lg"
          className="w-full sm:w-auto sm:min-w-[160px]"
        >
          {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
          {t("firstRun.setup.submit")}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={handleSkip}
          disabled={isBusy}
          className="text-muted-foreground hover:text-foreground"
        >
          {t("firstRun.setup.skip")}
        </Button>
      </div>
    </div>
  )
}
