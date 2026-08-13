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
    // No border, no shadow, no backdrop-blur, and no scroll state. The bar
    // separates from the page by exactly one tonal step (`bg-card` on
    // `bg-surface`), which is how Anthropic does it and why theirs reads as a
    // publication rather than a 2016 navbar. It is also the cheap option:
    // `backdrop-filter` forces a full-screen readback every frame on the
    // mid-range Android our students actually use.
    <header className="sticky top-0 z-50 bg-card">
      <div className="container mx-auto max-w-[1400px] px-4">
        <div className="flex h-14 items-stretch justify-between gap-2 md:h-16 md:gap-6">
          <Link
            to="/"
            // The school's name, set like a masthead rather than a toolbar
            // label: this is the one place the serif carries the institution.
            className="flex shrink-0 items-center font-serif text-base font-semibold leading-none tracking-[-0.01em] text-ink decoration-transparent underline-offset-4 transition-[text-decoration-color] duration-200 hover:underline hover:decoration-ink/30 md:text-lg"
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
