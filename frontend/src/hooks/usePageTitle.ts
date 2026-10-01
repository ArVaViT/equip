import { useContext, useEffect } from "react"
import { useLocation } from "react-router-dom"
import { useTranslation } from "react-i18next"

import { AuthContext } from "@/context/auth-context"

/**
 * The translation key naming this path, or ``null`` when no rule claims it.
 *
 * Null is the catch-all route — a 404. Kept distinct from "matched" on
 * purpose: the guard in `__tests__/usePageTitle.test.ts` asserts that every
 * route in App.tsx is claimed here, and folding the fallback into this
 * function would make that assertion pass for a route nothing matches.
 */
export function matchTitleKey(pathname: string): string | null {
  const exact: Record<string, string> = {
    "/login": "pageTitle.login",
    "/register": "pageTitle.register",
    "/forgot-password": "pageTitle.forgotPassword",
    "/auth/reset-password": "pageTitle.resetPassword",
    "/auth/callback": "pageTitle.authCallback",
    "/auth/confirm": "pageTitle.authConfirm",
    "/dashboard": "pageTitle.dashboard",
    "/courses": "pageTitle.courses",
    "/profile": "pageTitle.profile",
    "/certificates": "pageTitle.certificates",
    "/calendar": "pageTitle.calendar",
    "/teacher": "pageTitle.teacher",
    "/admin": "pageTitle.admin",
    "/": "pageTitle.home",
    // Reusing the screens' own headings rather than minting `pageTitle.*`
    // twins: these are already translated into all four languages, and a
    // second copy is a second thing to keep in step.
    "/verify": "verify.title",
    "/unsubscribe": "unsubscribe.title",
    "/invite/accept": "invite.heading",
    "/teach/grading": "grading.title",
    "/daily-challenge/archive": "dailyChallenge.archive.title",
  }
  if (exact[pathname]) return exact[pathname]

  // A lesson is reachable both by its course alone and through the module
  // that groups it; both addresses name the same screen, so both name the
  // same tab. Written as one rule with the module segment optional rather
  // than as two, so a third caller cannot be added to one and missed on the
  // other.
  if (/^\/teacher\/courses\/[^/]+(?:\/modules\/[^/]+)?\/chapters\/[^/]+\/edit$/.test(pathname)) {
    return "pageTitle.editChapter"
  }
  if (/^\/teacher\/courses\/[^/]+\/modules\/[^/]+\/edit$/.test(pathname)) {
    return "pageTitle.editModule"
  }
  if (/^\/verify\/[^/]+$/.test(pathname)) return "verify.title"
  if (/^\/certificates\/[^/]+$/.test(pathname)) return "pageTitle.certificates"
  if (/^\/teacher\/courses\/[^/]+\/vedomost$/.test(pathname)) return "vedomost.title"
  if (/^\/teacher\/courses\/[^/]+\/gradebook$/.test(pathname)) return "pageTitle.gradebook"
  if (/^\/teacher\/courses\/[^/]+\/progress$/.test(pathname)) return "pageTitle.studentProgress"
  if (/^\/teacher\/courses\/[^/]+\/analytics$/.test(pathname)) return "pageTitle.courseAnalytics"
  if (pathname.startsWith("/teacher/courses/")) return "pageTitle.courseEditor"
  if (/^\/courses\/[^/]+(?:\/modules\/[^/]+)?\/chapters\/[^/]+$/.test(pathname)) return "pageTitle.chapter"
  if (/^\/courses\/[^/]+\/modules\//.test(pathname)) return "pageTitle.module"
  if (pathname.startsWith("/courses/")) return "pageTitle.course"
  if (pathname.startsWith("/admin")) return "pageTitle.admin"
  // Checked before /privacy, which would otherwise swallow it.
  if (pathname === "/privacy/providers") return "pageTitle.providers"
  if (pathname === "/privacy") return "pageTitle.privacy"
  if (pathname === "/dmca") return "dmca.title"
  if (pathname === "/terms") return "pageTitle.terms"
  if (pathname === "/teacher-terms") return "pageTitle.teacherTerms"
  if (pathname === "/school-agreement") return "pageTitle.schoolAgreement"

  return null
}

/**
 * True for a visitor on the landing page: `/` with nobody signed in. The
 * same address is the dashboard for everybody else. Read from the context
 * directly rather than through `useAuth`, which throws outside a provider —
 * a hook that names tabs has no business taking a page down.
 */
export function useGuestHome(pathname: string): boolean {
  const auth = useContext(AuthContext)
  return pathname === "/" && auth !== null && !auth.loading && !auth.user
}

/**
 * Names a page asked to be called by, keyed by the path they belong to.
 *
 * A course page titled «Курс — Equip» named nothing in the tab strip, the
 * history list or a bookmark, and a screen reader announced the same word on
 * every course. The page knows its own name only after it loads, so it hands
 * the name over here; a module-level map rather than state, because the
 * route-wide hook below runs after the page's own effect in the same commit
 * and must read it then, not a render later.
 */
const namedTitles = new Map<string, string>()

/** Title this page by its own name ("Деяния — Equip") once it has one. */
export function useNamedPageTitle(name: string | null | undefined) {
  const { pathname } = useLocation()
  const { t } = useTranslation()
  useEffect(() => {
    const trimmed = name?.trim()
    if (!trimmed) return
    namedTitles.set(pathname, trimmed)
    document.title = `${trimmed} — ${t("common.appName")}`
    return () => {
      namedTitles.delete(pathname)
    }
  }, [name, pathname, t])
}

export function usePageTitle() {
  const { pathname } = useLocation()
  const { t } = useTranslation()
  const guestHome = useGuestHome(pathname)

  useEffect(() => {
    // The landing page is the page a search result lands on, and it was
    // titled «Home — Equip» — the name of a tab inside the product, which
    // says nothing to somebody without an account. It keeps the title the
    // first frame already shows (`meta.documentTitle`, set by
    // `/locale-boot.js` before the bundle runs): the brand and what it is,
    // in the visitor's language, with the word people search for — which the
    // claim itself («in order, not in fragments») does not contain. The
    // claim is on the share card instead.
    if (guestHome) {
      document.title = t("meta.documentTitle")
      return
    }
    const named = namedTitles.get(pathname)
    if (named) {
      document.title = `${named} — ${t("common.appName")}`
      return
    }
    // A 404 that said only "Equip" was indistinguishable from a working page
    // in the tab strip, and announced nothing to a screen reader.
    const key = matchTitleKey(pathname) ?? "notFound.title"
    document.title = `${t(key)} — ${t("common.appName")}`
  }, [pathname, t, guestHome])
}
