import { useEffect } from "react"
import { useLocation } from "react-router-dom"
import { useTranslation } from "react-i18next"

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
    "/invite/accept": "invite.heading",
    "/teach/grading": "grading.title",
    "/daily-challenge/archive": "dailyChallenge.archive.title",
  }
  if (exact[pathname]) return exact[pathname]

  if (/^\/teacher\/courses\/[^/]+\/modules\/[^/]+\/chapters\/[^/]+\/edit$/.test(pathname)) {
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
  if (/^\/courses\/[^/]+\/modules\/[^/]+\/chapters\/[^/]+$/.test(pathname)) return "pageTitle.chapter"
  if (/^\/courses\/[^/]+\/modules\//.test(pathname)) return "pageTitle.module"
  if (pathname.startsWith("/courses/")) return "pageTitle.course"
  if (pathname.startsWith("/admin")) return "pageTitle.admin"
  if (pathname === "/privacy") return "pageTitle.privacy"
  if (pathname === "/terms") return "pageTitle.terms"

  return null
}

export function usePageTitle() {
  const { pathname } = useLocation()
  const { t } = useTranslation()

  useEffect(() => {
    // A 404 that said only "Equip" was indistinguishable from a working page
    // in the tab strip, and announced nothing to a screen reader.
    const key = matchTitleKey(pathname) ?? "notFound.title"
    document.title = `${t(key)} — ${t("common.appName")}`
  }, [pathname, t])
}
