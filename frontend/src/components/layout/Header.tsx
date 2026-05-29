import { useEffect, useState } from "react"
import { Link, useLocation } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { useAuth } from "@/context/useAuth"
import { ROLES } from "@/types"
import { HeaderDesktopNav } from "./header/HeaderDesktopNav"
import { HeaderMobileMenuTrigger } from "./header/HeaderMobileMenuTrigger"
import { HeaderMobileSheet } from "./header/HeaderMobileSheet"
import { HeaderUserMenu } from "./header/HeaderUserMenu"

/**
 * App-shell header — the sticky bar that sits on top of every routed
 * page. Composes four focused sub-components:
 *
 *   * <HeaderDesktopNav>    — top-bar primary navigation (>= md)
 *   * <HeaderUserMenu>      — bell + avatar / sign-in cluster (>= md)
 *   * <HeaderMobileMenuTrigger> — hamburger button (< md)
 *   * <HeaderMobileSheet>   — full mobile drawer (< md)
 *
 * The composer owns one piece of state — whether the mobile sheet is
 * open — and the cross-cutting "close-on-route-change" effect. The
 * brand link is inline because it's two lines and has no internal
 * state worth extracting.
 *
 * Splitting this file (Phase 5bb) replaced the previous 322-line
 * monolith. Each part now has a single visual responsibility and a
 * small prop surface; tests and storybook-style isolation become
 * feasible without touching the composer.
 */
export default function Header() {
  const { user } = useAuth()
  const location = useLocation()
  const { t } = useTranslation()
  const [mobileOpen, setMobileOpen] = useState(false)

  const isTeacher = user?.role === ROLES.TEACHER || user?.role === ROLES.ADMIN

  // Close the sheet on every route transition. Doing it here (not in
  // HeaderMobileSheet itself) keeps the sheet stateless w/r/t
  // navigation.
  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

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
            <HeaderDesktopNav isTeacher={isTeacher} role={user.role} />
          ) : (
            <div className="hidden flex-1 md:block" aria-hidden />
          )}

          <div className="flex shrink-0 items-center gap-1.5 md:gap-2">
            <HeaderUserMenu user={user} />
            <HeaderMobileMenuTrigger onOpen={() => setMobileOpen(true)} isOpen={mobileOpen} />
          </div>
        </div>
      </div>

      <HeaderMobileSheet
        open={mobileOpen}
        onOpenChange={setMobileOpen}
        user={user}
        isTeacher={isTeacher}
      />
    </header>
  )
}
