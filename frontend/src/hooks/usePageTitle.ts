import { useEffect } from "react"
import { useLocation } from "react-router-dom"
import { useTranslation } from "react-i18next"

function matchTitleKey(pathname: string): string | null {
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
  }
  if (exact[pathname]) return exact[pathname]

  if (/^\/teacher\/courses\/[^/]+\/modules\/[^/]+\/chapters\/[^/]+\/edit$/.test(pathname)) {
    return "pageTitle.editChapter"
  }
  if (/^\/teacher\/courses\/[^/]+\/modules\/[^/]+\/edit$/.test(pathname)) {
    return "pageTitle.editModule"
  }
  if (/^\/teacher\/courses\/[^/]+\/gradebook$/.test(pathname)) return "pageTitle.gradebook"
  if (/^\/teacher\/courses\/[^/]+\/progress$/.test(pathname)) return "pageTitle.studentProgress"
  if (/^\/teacher\/courses\/[^/]+\/analytics$/.test(pathname)) return "pageTitle.courseAnalytics"
  if (pathname.startsWith("/teacher/courses/")) return "pageTitle.courseEditor"
  if (/^\/courses\/[^/]+\/modules\/[^/]+\/chapters\/[^/]+$/.test(pathname)) return "pageTitle.chapter"
  if (/^\/courses\/[^/]+\/modules\//.test(pathname)) return "pageTitle.module"
  if (pathname.startsWith("/courses/")) return "pageTitle.course"
  if (pathname.startsWith("/admin")) return "pageTitle.admin"

  return null
}

export function usePageTitle() {
  const { pathname } = useLocation()
  const { t } = useTranslation()

  useEffect(() => {
    const key = matchTitleKey(pathname)
    document.title = key ? `${t(key)} — ${t("common.appName")}` : t("common.appName")
  }, [pathname, t])
}
