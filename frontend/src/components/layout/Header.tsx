import { lazy, Suspense, useEffect, useState } from "react"
import { Link, useLocation } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { LayoutGroup, motion, useReducedMotion } from "motion/react"
import { PressFeedback } from "@/components/motion"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { useAuth } from "@/context/useAuth"
import { ROLES } from "@/types"
import { User as UserIcon, Menu } from "lucide-react"
import { toProxyImage } from "@/lib/images"
import { cn } from "@/lib/utils"
import { EDITORIAL_EASE } from "@/lib/motion"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

const UNDERLINE_LAYOUT_ID = "header-active-underline"

const NotificationBell = lazy(() => import("./NotificationBell"))

const ICON_STROKE = 1.75 as const

function HeaderNavLink({
  to,
  active,
  children,
  onNavigate,
  variant = "bar",
}: {
  to: string
  active: boolean
  children: React.ReactNode
  onNavigate?: () => void
  variant?: "bar" | "sheet"
}) {
  const prefersReducedMotion = useReducedMotion()
  const isSheet = variant === "sheet"
  return (
    <Link
      to={to}
      onClick={onNavigate}
      className={cn(
        "font-medium transition-colors duration-200 ease-editorial",
        isSheet
          ? "flex min-h-10 w-full items-center border-l-2 border-transparent py-2 pl-[calc(0.75rem-2px)] pr-3 text-sm active:bg-muted/60"
          : "relative flex h-full items-center px-3 text-sm",
        isSheet &&
          (active
            ? "border-primary bg-muted/25 font-medium text-foreground"
            : "text-foreground hover:border-border hover:bg-muted/40"),
        !isSheet &&
          (active ? "text-foreground" : "text-muted-foreground hover:text-foreground"),
      )}
    >
      {children}
      {!isSheet &&
        active &&
        (prefersReducedMotion ? (
          <span
            className="pointer-events-none absolute inset-x-3 bottom-0 h-0.5 rounded-sm bg-primary"
            aria-hidden
          />
        ) : (
          <motion.span
            layoutId={UNDERLINE_LAYOUT_ID}
            className="pointer-events-none absolute inset-x-3 bottom-0 h-0.5 rounded-sm bg-primary"
            transition={{ duration: 0.32, ease: EDITORIAL_EASE }}
            aria-hidden
          />
        ))}
    </Link>
  )
}

export default function Header() {
  const { user } = useAuth()
  const location = useLocation()
  const { t } = useTranslation()
  const [mobileOpen, setMobileOpen] = useState(false)

  const isTeacher = user?.role === ROLES.TEACHER || user?.role === ROLES.ADMIN
  const isActive = (path: string) =>
    path === "/" ? location.pathname === "/" : location.pathname.startsWith(path)

  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  const closeMobile = () => setMobileOpen(false)

  return (
    <header className="sticky top-0 z-50 border-b border-border/90 bg-background/90 backdrop-blur-md supports-[backdrop-filter]:bg-background/75">
      <div className="container mx-auto max-w-[1400px] px-4">
        <div className="flex h-11 items-stretch justify-between gap-2 md:h-12 md:gap-4">
          <Link
            to="/"
            className="flex shrink-0 items-center font-serif text-sm font-semibold leading-none tracking-tight text-foreground transition-opacity hover:opacity-85 md:text-base"
          >
            {t("common.appName")}
          </Link>

          {user ? (
            <LayoutGroup id="header-nav">
              <nav
                data-tour="header-nav"
                className="hidden min-w-0 flex-1 flex-wrap items-stretch justify-center md:flex"
                aria-label={t("header.navAriaLabel")}
              >
                <HeaderNavLink to="/" active={location.pathname === "/"}>
                  {t("header.home")}
                </HeaderNavLink>
                <HeaderNavLink to="/courses" active={isActive("/courses")}>
                  {t("header.courses")}
                </HeaderNavLink>
                <HeaderNavLink to="/calendar" active={isActive("/calendar")}>
                  {t("header.calendar")}
                </HeaderNavLink>
                <HeaderNavLink to="/certificates" active={isActive("/certificates")}>
                  {t("header.certificates")}
                </HeaderNavLink>
                {isTeacher && (
                  // header.manage / header.admin are the COMPACT (desktop bar) labels
                  // for the same destinations as header.manageCourses / header.adminPanel
                  // used in the mobile sheet. Two keys per destination is intentional:
                  // the bar is space-constrained, the sheet has room for a verbose label.
                  // Don't unify these — see UI-DECISIONS.md.
                  <HeaderNavLink to="/teacher" active={isActive("/teacher")}>
                    {t("header.manage")}
                  </HeaderNavLink>
                )}
                {user.role === ROLES.ADMIN && (
                  <HeaderNavLink to="/admin" active={isActive("/admin")}>
                    {t("header.admin")}
                  </HeaderNavLink>
                )}
              </nav>
            </LayoutGroup>
          ) : (
            <div className="hidden flex-1 md:block" aria-hidden />
          )}

          <div className="flex shrink-0 items-center gap-1.5 md:gap-2">
            <div className="hidden items-center gap-1 md:flex">
              {user ? (
                <>
                  <Suspense fallback={<div className="h-7 w-7 shrink-0" aria-hidden />}>
                    <NotificationBell />
                  </Suspense>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Link to="/profile" data-tour="header-profile" className="inline-flex">
                        <PressFeedback className="inline-flex">
                          <Button
                            variant={isActive("/profile") ? "secondary" : "ghost"}
                            size="sm"
                            className="h-7 w-7 shrink-0 rounded-full p-0"
                            aria-label={t("header.profile")}
                          >
                            {user.avatar_url ? (
                              <img
                                src={toProxyImage(user.avatar_url)}
                                alt=""
                                className="h-6 w-6 rounded-full object-cover"
                                onError={(e) => {
                                  e.currentTarget.style.display = "none"
                                }}
                              />
                            ) : (
                              <UserIcon
                                className="h-3.5 w-3.5"
                                strokeWidth={ICON_STROKE}
                                aria-hidden="true"
                              />
                            )}
                          </Button>
                        </PressFeedback>
                      </Link>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" sideOffset={8}>
                      <p>{t("header.profile")}</p>
                    </TooltipContent>
                  </Tooltip>
                </>
              ) : (
                <>
                  <Link to="/login">
                    <Button variant="ghost" size="sm" className="h-8 px-2.5 text-xs font-medium leading-none">
                      {t("common.signIn")}
                    </Button>
                  </Link>
                  <Link to="/register">
                    <Button size="sm" className="h-8 px-3 text-xs font-medium leading-none">
                      {t("common.register")}
                    </Button>
                  </Link>
                </>
              )}
            </div>

            <div className="flex md:hidden">
              <Tooltip>
                <TooltipTrigger asChild>
                  <PressFeedback className="inline-flex">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-8 min-w-8 px-1 text-muted-foreground hover:text-foreground"
                      onClick={() => setMobileOpen(true)}
                      aria-label={t("header.menu")}
                      aria-expanded={mobileOpen}
                    >
                      <Menu className="h-4 w-4" strokeWidth={ICON_STROKE} aria-hidden="true" />
                    </Button>
                  </PressFeedback>
                </TooltipTrigger>
                <TooltipContent side="bottom" sideOffset={8}>
                  <p>{t("header.menu")}</p>
                </TooltipContent>
              </Tooltip>
            </div>
          </div>
        </div>
      </div>

      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent
          side="right"
          className="flex max-h-[100dvh] flex-col gap-0 overflow-hidden p-0"
        >
          <SheetHeader className="shrink-0 px-5 pb-3 pt-5">
            <SheetTitle className="font-sans text-sm font-semibold tracking-normal text-foreground">
              {t("header.mobileMenuTitle")}
            </SheetTitle>
            <SheetDescription className="sr-only">{t("header.mobileMenuDescription")}</SheetDescription>
          </SheetHeader>
          <div className="flex min-h-0 flex-1 flex-col">
            <nav
              className="flex flex-col gap-0.5 overflow-y-auto px-4 pb-2 pt-1"
              aria-label={t("header.navAriaLabel")}
            >
              {user ? (
                <>
                  <HeaderNavLink variant="sheet" to="/" active={location.pathname === "/"} onNavigate={closeMobile}>
                    {t("header.home")}
                  </HeaderNavLink>
                  <HeaderNavLink variant="sheet" to="/courses" active={isActive("/courses")} onNavigate={closeMobile}>
                    {t("header.courses")}
                  </HeaderNavLink>
                  <HeaderNavLink variant="sheet" to="/calendar" active={isActive("/calendar")} onNavigate={closeMobile}>
                    {t("header.calendar")}
                  </HeaderNavLink>
                  <HeaderNavLink
                    variant="sheet"
                    to="/certificates"
                    active={isActive("/certificates")}
                    onNavigate={closeMobile}
                  >
                    {t("header.certificates")}
                  </HeaderNavLink>
                  {isTeacher && (
                    // header.manageCourses / header.adminPanel are the VERBOSE (mobile sheet)
                    // labels — paired intentionally with the compact header.manage /
                    // header.admin used in the desktop bar above. See UI-DECISIONS.md.
                    <HeaderNavLink variant="sheet" to="/teacher" active={isActive("/teacher")} onNavigate={closeMobile}>
                      {t("header.manageCourses")}
                    </HeaderNavLink>
                  )}
                  {user.role === ROLES.ADMIN && (
                    <HeaderNavLink variant="sheet" to="/admin" active={isActive("/admin")} onNavigate={closeMobile}>
                      {t("header.adminPanel")}
                    </HeaderNavLink>
                  )}
                  <div className="mt-2 border-t border-border/80 pt-2">
                    <Suspense fallback={null}>
                      <NotificationBell
                        triggerVariant="navRow"
                        panelVariant="sheet"
                        onNotificationNavigate={() => setMobileOpen(false)}
                      />
                    </Suspense>
                  </div>
                  <Link
                    to="/profile"
                    className={cn(
                      "flex min-h-10 w-full items-center rounded-md px-3 text-sm font-medium transition-colors hover:bg-muted active:bg-muted/80",
                      isActive("/profile")
                        ? "bg-muted/60 text-foreground"
                        : "text-foreground",
                    )}
                    aria-current={isActive("/profile") ? "page" : undefined}
                    onClick={closeMobile}
                  >
                    {t("header.profileAndSettings")}
                  </Link>
                </>
              ) : (
                <>
                  <HeaderNavLink variant="sheet" to="/courses" active={isActive("/courses")} onNavigate={closeMobile}>
                    {t("header.courses")}
                  </HeaderNavLink>
                  <HeaderNavLink variant="sheet" to="/login" active={isActive("/login")} onNavigate={closeMobile}>
                    {t("common.signIn")}
                  </HeaderNavLink>
                  <Link
                    to="/register"
                    className="flex min-h-10 w-full items-center rounded-md px-3 text-sm font-semibold text-primary transition-colors hover:bg-muted active:bg-muted/80"
                    onClick={closeMobile}
                  >
                    {t("common.register")}
                  </Link>
                </>
              )}
            </nav>
            <div className="mt-auto border-t border-border/80 px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3">
              <p className="text-xs text-muted-foreground">{t("common.appName")}</p>
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </header>
  )
}
