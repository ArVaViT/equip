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
import { formatDate } from "@/i18n/format"
import { toast } from "@/lib/toast"
import {
  User as UserIcon, Mail, Shield, Calendar, Camera, Globe,
  Loader2, Award, BookOpen, ArrowRight, LogOut, Moon, Sun,
} from "lucide-react"

const EDITORIAL_EASE = [0.22, 1, 0.36, 1] as const

function useCountUp(target: number, durationMs = 800) {
  const prefersReducedMotion = useReducedMotion()
  const [displayed, setDisplayed] = useState(0)
  useEffect(() => {
    if (prefersReducedMotion || target <= 0) {
      setDisplayed(target)
      return
    }
    const steps = Math.min(24, Math.max(target, 6))
    const stepMs = durationMs / steps
    let i = 0
    setDisplayed(0)
    const id = window.setInterval(() => {
      i++
      setDisplayed(Math.min(target, Math.round((target * i) / steps)))
      if (i >= steps) window.clearInterval(id)
    }, stepMs)
    return () => window.clearInterval(id)
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
  const [certificateCount, setCertificateCount] = useState(0)
  const [completedCount, setCompletedCount] = useState(0)
  const animatedCompleted = useCountUp(completedCount)
  const animatedCertificates = useCountUp(certificateCount)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!user?.id) return
    let cancelled = false
    const loadStats = async () => {
      try {
        const [certs, enrollments] = await Promise.all([
          coursesService.getMyCertificates().catch(() => []),
          coursesService.getMyCourses().catch(() => []),
        ])
        if (cancelled) return
        setCertificateCount(certs.length)
        setCompletedCount(enrollments.filter((e) => e.progress >= 100).length)
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

  const handleLogout = () => {
    logout()
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

  const initials = (user.full_name ?? user.email)
    .split(/[\s@]/)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase())
    .join("")

  return (
    <div className="container mx-auto max-w-3xl px-4 py-8 md:px-6">
      <div className="stagger-fade-in space-y-6">
        <Card className="overflow-hidden transition-[border-color] duration-200 hover:border-primary/25">
          <CardHeader className="border-b border-border bg-gradient-accent-subtle">
            <div className="flex flex-col gap-6 sm:flex-row sm:items-start">
              <div className="relative shrink-0">
                {user.avatar_url ? (
                  <img
                    src={toProxyImage(user.avatar_url)}
                    alt={t("profile.avatarAlt", { name: user.full_name ?? user.email })}
                    loading="lazy"
                    className="h-20 w-20 rounded-full border border-border object-cover ring-2 ring-background"
                  />
                ) : (
                  <div className="flex h-20 w-20 items-center justify-center rounded-full border border-border bg-muted font-serif text-xl font-semibold text-foreground">
                    {initials || <UserIcon className="h-9 w-9 text-muted-foreground" strokeWidth={1.75} aria-hidden />}
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  disabled={uploading}
                  aria-label={t("profile.changeAvatar")}
                  className="absolute -bottom-0.5 -right-0.5 flex h-7 w-7 cursor-pointer items-center justify-center rounded-full border border-border bg-card text-foreground shadow-none transition-colors hover:bg-muted disabled:pointer-events-none"
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
                <InlineEdit
                  size="h2"
                  value={user.full_name ?? ""}
                  onSave={handleSaveName}
                  required
                  maxLength={150}
                  placeholder={t("profile.fullName")}
                  ariaLabel={t("profile.editName")}
                  textClassName="tracking-tight"
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

        <Card className="transition-[border-color] duration-200 hover:border-primary/25">
          <CardHeader className="space-y-1">
            <CardTitle className="font-serif text-lg font-semibold tracking-tight">
              {t("profile.learningProgress")}
            </CardTitle>
            <CardDescription>{t("profile.learningProgressDescription")}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="flex items-center gap-3 rounded-md border border-border bg-muted/15 p-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-md bg-muted">
                  <BookOpen className="h-5 w-5 text-muted-foreground" strokeWidth={1.75} aria-hidden />
                </div>
                <div>
                  <p className="text-2xl font-semibold leading-none tabular-nums">{animatedCompleted}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{t("profile.coursesCompleted")}</p>
                </div>
              </div>
              <div className="flex items-center gap-3 rounded-md border border-border bg-muted/15 p-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-md bg-muted">
                  <Award className="h-5 w-5 text-muted-foreground" strokeWidth={1.75} aria-hidden />
                </div>
                <div>
                  <p className="text-2xl font-semibold leading-none tabular-nums">{animatedCertificates}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{t("profile.certificatesEarned")}</p>
                </div>
              </div>
            </div>
            {certificateCount > 0 && (
              <Link
                to="/certificates"
                className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-primary underline-offset-4 hover:underline"
              >
                {t("profile.viewAllCertificates")}
                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              </Link>
            )}
          </CardContent>
        </Card>

        <Card className="transition-[border-color] duration-200 hover:border-primary/25">
          <CardHeader>
            <CardTitle className="font-serif text-lg font-semibold tracking-tight">{t("profile.accountDetails")}</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="divide-y divide-border rounded-md border border-border">
              <div className="flex items-start gap-3 px-4 py-3">
                <Mail className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} aria-hidden />
                <div className="min-w-0">
                  <dt className="text-xs text-muted-foreground">{t("auth.email")}</dt>
                  <dd className="text-sm font-medium">{user.email}</dd>
                </div>
              </div>
              <div className="flex items-start gap-3 px-4 py-3">
                <Shield className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} aria-hidden />
                <div>
                  <dt className="text-xs text-muted-foreground">{t("profile.role")}</dt>
                  <dd className="text-sm font-medium">{t(ROLE_I18N_KEY[user.role])}</dd>
                </div>
              </div>
              {user.created_at && (
                <div className="flex items-start gap-3 px-4 py-3">
                  <Calendar className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} aria-hidden />
                  <div>
                    <dt className="text-xs text-muted-foreground">{t("profile.memberSince")}</dt>
                    <dd className="text-sm font-medium">
                      {formatDate(user.created_at, {
                        year: "numeric",
                        month: "long",
                        day: "numeric",
                      })}
                    </dd>
                  </div>
                </div>
              )}
            </dl>
          </CardContent>
        </Card>

        <Card className="transition-[border-color] duration-200 hover:border-primary/25">
          <CardHeader>
            <CardTitle className="font-serif text-lg font-semibold tracking-tight">{t("profile.preferences")}</CardTitle>
          </CardHeader>
          <CardContent className="divide-y divide-border rounded-md border border-border px-0">
            <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-4">
              <div className="flex min-w-0 items-center gap-3">
                {theme === "dark" ? (
                  <Moon className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} aria-hidden />
                ) : (
                  <Sun className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} aria-hidden />
                )}
                <div className="min-w-0">
                  <p className="text-sm font-medium">{t("profile.theme")}</p>
                  <p className="text-xs text-muted-foreground">
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
                      transition={{ duration: 0.22, ease: EDITORIAL_EASE }}
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
                <Globe className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} aria-hidden />
                <div className="min-w-0">
                  <p className="text-sm font-medium">{t("language.label")}</p>
                  <p className="text-xs text-muted-foreground">
                    {user.preferred_locale === "en" ? t("language.english") : t("language.russian")}
                  </p>
                </div>
              </div>
              <LanguageSwitcher />
            </div>
          </CardContent>
        </Card>

        <div className="border-t border-border pt-6">
          <Button
            variant="outline"
            className="w-full border-destructive/35 text-destructive transition-colors duration-200 hover:bg-destructive/10 hover:text-destructive"
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
