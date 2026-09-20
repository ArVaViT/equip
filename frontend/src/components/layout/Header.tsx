import { useEffect, useState } from "react"
import { Link, useLocation } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { useAuth } from "@/context/useAuth"
import { canTeach } from "@/lib/roles"
import { cn } from "@/lib/utils"
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
 * Splitting this file replaced the previous 322-line
 * monolith. Each part now has a single visual responsibility and a
 * small prop surface; tests and storybook-style isolation become
 * feasible without touching the composer.
 */
export default function Header() {
  const { user } = useAuth()
  const location = useLocation()
  const { t } = useTranslation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)

  const isTeacher = canTeach(user?.role)

  // The landing hero is a full-bleed WebGL scene, and a solid bar with a
  // hairline across the top of it cuts the picture in half — the scene
  // starts *under a shelf* instead of filling the screen. So on that one
  // page, for signed-out visitors only, the bar floats transparent over the
  // hero and takes its surface once the hero is behind you.
  //
  // This is the exception the comment below admits to not wanting, and it is
  // scoped as narrowly as it can be: one route, one audience. Every other
  // page keeps the hairline, and nothing here adds `backdrop-filter`.
  const overHero = location.pathname === "/" && !user
  const transparent = overHero && !scrolled

  useEffect(() => {
    if (!overHero) return
    const onScroll = () => setScrolled(window.scrollY > 24)
    onScroll()
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [overHero])

  // Close the sheet on every route transition. Doing it here (not in
  // HeaderMobileSheet itself) keeps the sheet stateless w/r/t
  // navigation.
  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  return (
    // A hairline, no shadow, no backdrop-blur, no scroll state.
    //
    // The bar used to separate from the page by a tonal step alone. That works
    // when the page is tinted and the bar is a different tint; it stops working
    // now that cards are white — the bar and the content merge. Every reference
    // measured has a hairline: Linear's is 1px at 8% white, and it is doing the
    // same job.
    //
    // Still no blur. `backdrop-filter` forces a full-screen readback every
    // frame on the mid-range Android our students actually read on, and it
    // buys nothing over a solid surface plus a line.
    <header
      className={cn(
        "sticky top-0 z-50 transition-colors duration-base ease-out",
        transparent ? "border-b border-transparent bg-transparent" : "border-b border-edge bg-surface",
      )}
    >
      <div className="container mx-auto max-w-[1400px] px-4">
        <div className="flex h-14 items-center justify-between gap-3 md:h-16 md:gap-8">
          <Link
            to="/"
            // The serif stays, and it is the only serif in the bar. Set beside
            // grotesque navigation it reads as a masthead — the WSJ move — where
            // a serif logo above serif links would just read as old.
            className="flex shrink-0 items-center font-serif text-lg font-semibold leading-none tracking-[-0.02em] text-ink transition-opacity duration-fast hover:opacity-70"
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
