import { useState, useRef, useEffect } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import PageSpinner from "@/components/ui/PageSpinner"
import { Button } from "@/components/ui/button"
import { InlineEdit } from "@/components/patterns"
import LanguageSwitcher from "@/components/layout/LanguageSwitcher"
import { useAuth } from "@/context/useAuth"
import { useTheme } from "@/context/useTheme"
import { usersService } from "@/services/users"
import { storageService } from "@/services/storage"
import { coursesService } from "@/services/courses"
import { makeProfileSchema } from "@/lib/validations/course"
import { toProxyImage } from "@/lib/images"
import { ROLE_I18N_KEY } from "@/lib/roles"
import { formatDateLong } from "@/i18n/format"
import { toast } from "@/lib/toast"
import {
  User as UserIcon, Mail, Calendar, Camera, Globe,
  Loader2, Award, BookOpen, ArrowRight, LogOut, Moon, Sun,
} from "lucide-react"
import { useUserTour } from "@/hooks/useUserTour"
import { profileSteps } from "@/lib/tourSteps"
import { EDITORIAL_EASE, MOTION_DURATION } from "@/lib/motion"
import { initialsOf } from "@/lib/names"

function useCountUp(target: number, durationMs = 800) {
  const prefersReducedMotion = useReducedMotion()
  // Initialize to ``target`` (not 0) so the first render — and StrictMode's
  // double-mount — never flashes through the animation. The effect only
  // fires the count-up when the target genuinely changes from the last
  // animated value, animating from the current display rather than from
  // zero so a stat going 5→7 doesn't snap back to 0 first.
  const [displayed, setDisplayed] = useState(target)
  const lastAnimatedRef = useRef(target)

  useEffect(() => {
    if (lastAnimatedRef.current === target) return
    if (prefersReducedMotion || target <= 0) {
      setDisplayed(target)
      lastAnimatedRef.current = target
      return
    }
    // Animate from the previously-animated value (not from current
    // ``displayed``, which would require a render-time ref read that
    // the react-hooks/refs lint rule rightly forbids). On first
    // genuine change ``lastAnimatedRef.current`` is the initial
    // ``target`` the hook was mounted with (typically 0), so the
    // animation behaves the same as the original interval-based
    // implementation without any 0-flash on remount.
    const from = lastAnimatedRef.current
    lastAnimatedRef.current = target
    let raf = 0
    const startTime = performance.now()
    const step = (now: number) => {
      const progress = Math.min(1, (now - startTime) / durationMs)
      setDisplayed(Math.round(from + (target - from) * progress))
      if (progress < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target, durationMs, prefersReducedMotion])
  return displayed
}

export default function ProfilePage() {
  const { user, refreshUser, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const prefersReducedMotion = useReducedMotion()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [error, setError] = useState("")
  const [uploading, setUploading] = useState(false)
  //: `null` until known, and again if the request fails. A statistic nobody
  //: could read is not zero.
  const [certificateCount, setCertificateCount] = useState<number | null>(null)
  const [completedCount, setCompletedCount] = useState<number | null>(null)
  const animatedCompleted = useCountUp(completedCount ?? 0)
  const animatedCertificates = useCountUp(certificateCount ?? 0)
  const fileRef = useRef<HTMLInputElement>(null)
  useUserTour({
    tourId: "profile-v1",
    steps: profileSteps(t),
    ready: !!user,
  })

  useEffect(() => {
    if (!user?.id) return
    let cancelled = false
    const loadStats = async () => {
      try {
        // `null`, not `[]`. These two numbers are the page's claim about what
        // somebody has achieved, and they animate up from zero — so a failed
        // request told a student with three certificates, emphatically and
        // with a count-up, that they had none.
        const [certs, enrollments] = await Promise.all([
          coursesService.getMyCertificates().catch(() => null),
          coursesService.getMyCourses().catch(() => null),
        ])
        if (cancelled) return
        setCertificateCount(certs === null ? null : certs.length)
        setCompletedCount(
          enrollments === null ? null : enrollments.filter((e) => e.progress >= 100).length,
        )
      } catch { /* non-critical */ }
    }
    loadStats()
    return () => { cancelled = true }
  }, [user?.id])

  const handleAvatarChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !user) return

    if (file.size > 2 * 1024 * 1024) {
      setError(t("profile.imageTooLarge"))
      return
    }

    setUploading(true)
    setError("")
    try {
      const url = await storageService.uploadAvatar(user.id, file)
      await usersService.updateProfile({ avatar_url: url })
      await refreshUser()
    } catch {
      setError(t("profile.uploadFailed"))
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ""
    }
  }

  const handleLogout = async () => {
    // ``logout`` is async (it round-trips through supabase.auth.signOut);
    // navigating before it resolves leaves a window where AuthContext
    // still has the old user but the redirect has already fired,
    // letting a stale "loading" flash through the login screen. Await
    // the signOut explicitly.
    await logout()
    navigate("/login", { replace: true })
  }

  const handleSaveName = async (next: string) => {
    const result = makeProfileSchema().safeParse({ full_name: next })
    if (!result.success) {
      toast({
        title: result.error.issues[0]?.message ?? t("profile.invalidInput"),
        variant: "destructive",
      })
      throw new Error("validation")
    }
    try {
      await usersService.updateProfile({ full_name: result.data.full_name })
      await refreshUser()
    } catch {
      toast({ title: t("profile.updateFailed"), variant: "destructive" })
      throw new Error("save")
    }
  }

  if (!user) {
    return <PageSpinner />
  }

  const initials = initialsOf(user.full_name ?? user.email)

  return (
    <div className="container mx-auto max-w-3xl px-4 py-8 md:px-6">
      <div data-tour="profile-form" className="stagger-fade-in space-y-6">
        <Card className="overflow-hidden transition-[border-color] duration-200 hover:border-brand/25">
          <CardHeader className="border-b border-edge bg-gradient-accent-subtle">
            <div className="flex flex-col gap-6 sm:flex-row sm:items-start">
              <div className="relative shrink-0">
                {user.avatar_url ? (
                  <img
                    src={toProxyImage(user.avatar_url)}
                    alt={t("profile.avatarAlt", { name: user.full_name ?? user.email })}
                    loading="lazy"
                    className="h-20 w-20 rounded-full object-cover ring-2 ring-background"
                  />
                ) : (
                  <div className="flex h-20 w-20 items-center justify-center rounded-full bg-muted font-serif text-xl font-semibold text-ink">
                    {initials || <UserIcon className="h-9 w-9 text-ink-muted" strokeWidth={1.75} aria-hidden />}
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  disabled={uploading}
                  aria-label={t("profile.changeAvatar")}
                  className="absolute -bottom-0.5 -right-0.5 flex h-7 w-7 cursor-pointer items-center justify-center rounded-full bg-card text-ink shadow-none transition-colors hover:bg-muted disabled:pointer-events-none"
                >
                  {uploading ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} aria-hidden />
                  ) : (
                    <Camera className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                  )}
                </button>
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/gif"
                  className="hidden"
                  onChange={handleAvatarChange}
                />
              </div>
              <div className="min-w-0 flex-1 space-y-0.5">
                {/* The user's full name doubles as the page's h1 — every
                    profile is "about this person", so their name is the
                    natural document heading. Sub-cards below use CardTitle. */}
                <InlineEdit
                  size="h1"
                  value={user.full_name ?? ""}
                  onSave={handleSaveName}
                  required
                  maxLength={150}
                  placeholder={t("profile.fullName")}
                  ariaLabel={t("profile.editName")}
                  textClassName="text-xl md:text-2xl tracking-tight"
                />
                <CardDescription className="text-sm">{t(ROLE_I18N_KEY[user.role])}</CardDescription>
              </div>
            </div>
          </CardHeader>
          {error && (
            <CardContent className="pt-6">
              <p className="text-sm text-destructive">{error}</p>
            </CardContent>
          )}
        </Card>

        <Card className="transition-[border-color] duration-200 hover:border-brand/25">
          <CardHeader className="space-y-1">
            <CardTitle>
              {t("profile.learningProgress")}
            </CardTitle>
            <CardDescription>{t("profile.learningProgressDescription")}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="flex items-center gap-3 rounded-md bg-muted/15 p-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-md bg-muted">
                  <BookOpen className="h-5 w-5 text-ink-muted" strokeWidth={1.75} aria-hidden />
                </div>
                <div>
                  <p className="text-2xl font-semibold leading-none tabular-nums">
                    {completedCount === null ? "—" : animatedCompleted}
                  </p>
                  <p className="mt-1 text-xs text-ink-muted">{t("profile.coursesCompleted")}</p>
                </div>
              </div>
              <div className="flex items-center gap-3 rounded-md bg-muted/15 p-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-md bg-muted">
                  <Award className="h-5 w-5 text-ink-muted" strokeWidth={1.75} aria-hidden />
                </div>
                <div>
                  <p className="text-2xl font-semibold leading-none tabular-nums">
                    {certificateCount === null ? "—" : animatedCertificates}
                  </p>
                  <p className="mt-1 text-xs text-ink-muted">{t("profile.certificatesEarned")}</p>
                </div>
              </div>
            </div>
            {certificateCount !== null && certificateCount > 0 && (
              <Link
                to="/certificates"
                className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-brand underline-offset-4 hover:underline"
              >
                {t("profile.viewAllCertificates")}
                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              </Link>
            )}
          </CardContent>
        </Card>

        <Card className="transition-[border-color] duration-200 hover:border-brand/25">
          <CardHeader>
            <CardTitle>{t("profile.accountDetails")}</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="divide-y divide-border rounded-md ">
              <div className="flex items-start gap-3 px-4 py-3">
                <Mail className="mt-0.5 h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
                <div className="min-w-0">
                  <dt className="text-xs text-ink-muted">{t("auth.email")}</dt>
                  <dd className="text-sm font-medium">{user.email}</dd>
                </div>
              </div>
              {user.created_at && (
                <div className="flex items-start gap-3 px-4 py-3">
                  <Calendar className="mt-0.5 h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
                  <div>
                    <dt className="text-xs text-ink-muted">{t("profile.memberSince")}</dt>
                    <dd className="text-sm font-medium">
                      {formatDateLong(user.created_at)}
                    </dd>
                  </div>
                </div>
              )}
            </dl>
          </CardContent>
        </Card>

        <Card className="transition-[border-color] duration-200 hover:border-brand/25">
          <CardHeader>
            <CardTitle>{t("profile.preferences")}</CardTitle>
          </CardHeader>
          <CardContent className="divide-y divide-border rounded-md px-0">
            <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-4">
              <div className="flex min-w-0 items-center gap-3">
                {theme === "dark" ? (
                  <Moon className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
                ) : (
                  <Sun className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
                )}
                <div className="min-w-0">
                  <p className="text-sm font-medium">{t("profile.theme")}</p>
                  <p className="text-xs text-ink-muted">
                    {theme === "dark" ? t("profile.themeDark") : t("profile.themeLight")}
                  </p>
                </div>
              </div>
              <Button variant="outline" size="sm" onClick={toggleTheme}>
                {prefersReducedMotion ? (
                  theme === "dark" ? (
                    <Sun className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
                  ) : (
                    <Moon className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
                  )
                ) : (
                  <AnimatePresence mode="wait" initial={false}>
                    <motion.span
                      key={theme}
                      className="mr-1.5 inline-flex"
                      initial={{ rotate: -45, opacity: 0 }}
                      animate={{ rotate: 0, opacity: 1 }}
                      exit={{ rotate: 45, opacity: 0 }}
                      transition={{ duration: MOTION_DURATION.base, ease: EDITORIAL_EASE }}
                    >
                      {theme === "dark" ? (
                        <Sun className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                      ) : (
                        <Moon className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                      )}
                    </motion.span>
                  </AnimatePresence>
                )}
                {theme === "dark" ? t("profile.switchToLight") : t("profile.switchToDark")}
              </Button>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-4">
              <div className="flex min-w-0 items-center gap-3">
                <Globe className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
                <div className="min-w-0">
                  <p className="text-sm font-medium">{t("language.label")}</p>
                  <p className="text-xs text-ink-muted">
                    {user.preferred_locale === "en" ? t("language.english") : t("language.russian")}
                  </p>
                </div>
              </div>
              <LanguageSwitcher />
            </div>
          </CardContent>
        </Card>

        {/* The two documents used to hang off the app-shell footer. That
            footer is gone — an application does not have one — so they live
            here, one click from the avatar, which is where a signed-in person
            looks for their own account's terms. They remain public at
            `/privacy` and `/terms` for everybody else. */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-edge pt-5 text-sm">
          <Link
            to="/privacy"
            className="text-ink-muted underline-offset-4 transition-colors duration-fast hover:text-ink hover:underline"
          >
            {t("legal.privacy")}
          </Link>
          <Link
            to="/terms"
            className="text-ink-muted underline-offset-4 transition-colors duration-fast hover:text-ink hover:underline"
          >
            {t("legal.terms")}
          </Link>
        </div>

        <div className="pt-2">
          <Button
            variant="outline"
            className="w-full border-destructive/35 text-destructive-ink transition-colors duration-200 hover:bg-destructive/10 hover:text-destructive-ink"
            onClick={handleLogout}
          >
            <LogOut className="mr-2 h-4 w-4" strokeWidth={1.75} aria-hidden />
            {t("common.signOut")}
          </Button>
        </div>
      </div>
    </div>
  )
}
