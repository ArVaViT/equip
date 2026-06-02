import { lazy, Suspense } from "react"
import { Link, useLocation } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { cn } from "@/lib/utils"
import { ROLES, type User } from "@/types"
import { HeaderNavLink } from "./HeaderNavLink"

const NotificationBell = lazy(() => import("../NotificationBell"))

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  user: User | null
  isTeacher: boolean
}

/**
 * Mobile drawer. Mirrors the desktop nav but with VERBOSE labels
 * (``header.manageCourses`` / ``header.adminPanel``) — see the note
 * on HeaderDesktopNav for why the two locales of label exist.
 *
 * NotificationBell is rendered with ``triggerVariant="navRow"`` +
 * ``panelVariant="sheet"`` so the panel opens inline (no floating
 * overlay above the next nav row) — see Phase 5ah.
 */
export function HeaderMobileSheet({ open, onOpenChange, user, isTeacher }: Props) {
  const { t } = useTranslation()
  const location = useLocation()
  const isActive = (path: string) =>
    path === "/" ? location.pathname === "/" : location.pathname.startsWith(path)
  const closeMobile = () => onOpenChange(false)

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex max-h-[100dvh] flex-col gap-0 overflow-hidden p-0">
        <SheetHeader className="shrink-0 px-5 pb-3 pt-5">
          <SheetTitle className="font-sans text-sm font-semibold tracking-normal text-ink">
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
                  <HeaderNavLink variant="sheet" to="/teacher" active={isActive("/teacher")} onNavigate={closeMobile}>
                    {t("header.manageCourses")}
                  </HeaderNavLink>
                )}
                {user.role === ROLES.ADMIN && (
                  <HeaderNavLink variant="sheet" to="/admin" active={isActive("/admin")} onNavigate={closeMobile}>
                    {t("header.adminPanel")}
                  </HeaderNavLink>
                )}
                <div className="mt-2 border-t border-edge/80 pt-2">
                  <Suspense fallback={null}>
                    <NotificationBell
                      triggerVariant="navRow"
                      panelVariant="sheet"
                      onNotificationNavigate={closeMobile}
                    />
                  </Suspense>
                </div>
                <Link
                  to="/profile"
                  className={cn(
                    "flex min-h-10 w-full items-center rounded-md px-3 text-sm font-medium transition-colors hover:bg-muted active:bg-muted/80",
                    isActive("/profile") ? "bg-muted/60 text-ink" : "text-ink",
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
                  className="flex min-h-10 w-full items-center rounded-md px-3 text-sm font-semibold text-brand transition-colors hover:bg-muted active:bg-muted/80"
                  onClick={closeMobile}
                >
                  {t("common.register")}
                </Link>
              </>
            )}
          </nav>
          <div className="mt-auto border-t border-edge/80 px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3">
            <p className="text-xs text-ink-muted">{t("common.appName")}</p>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
