import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Mail } from "lucide-react"
import { useAuth } from "@/context/useAuth"
import { SUPPORT_EMAIL } from "@/lib/brand"
import { ROLES } from "@/types"

export default function Footer() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const year = new Date().getFullYear()
  const showTeacherDashboard = user?.role === ROLES.TEACHER || user?.role === ROLES.ADMIN
  const isAdmin = user?.role === ROLES.ADMIN

  const linkClass =
    "text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-sm"

  const sep = <span className="select-none text-border" aria-hidden>|</span>

  return (
    <footer className="mt-auto border-t border-border bg-background/95">
      <div className="container mx-auto max-w-[1400px] px-4 py-4 md:px-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:gap-x-6 sm:gap-y-2">
          <div className="flex min-w-0 flex-col gap-0.5 sm:flex-row sm:items-baseline sm:gap-2">
            <Link
              to="/"
              className="shrink-0 font-serif text-sm font-semibold tracking-tight text-foreground transition-opacity hover:opacity-85"
            >
              {t("common.appName")}
            </Link>
            <span className="hidden text-muted-foreground/50 sm:inline" aria-hidden>
              ·
            </span>
            <p className="max-w-prose text-xs leading-snug text-muted-foreground sm:truncate">
              {t("footer.tagline")}
            </p>
          </div>

          <nav
            className="flex flex-wrap items-center gap-x-1 gap-y-1 text-xs sm:text-sm"
            aria-label={t("header.navAriaLabel")}
          >
            <Link to="/" className={linkClass}>
              {t("header.courses")}
            </Link>
            {sep}
            <Link to="/calendar" className={linkClass}>
              {t("header.calendar")}
            </Link>
            {sep}
            <Link to="/certificates" className={linkClass}>
              {t("header.certificates")}
            </Link>
            {user && showTeacherDashboard && (
              <>
                {sep}
                <Link to="/teacher" className={linkClass}>
                  {t("footer.teacherDashboard")}
                </Link>
              </>
            )}
            {user && isAdmin && (
              <>
                {sep}
                <Link to="/admin" className={linkClass}>
                  {t("header.adminPanel")}
                </Link>
              </>
            )}
            {sep}
            <a href={`mailto:${SUPPORT_EMAIL}`} className={`inline-flex items-center gap-1.5 ${linkClass}`}>
              <Mail className="h-3.5 w-3.5 shrink-0 opacity-70" strokeWidth={1.75} aria-hidden />
              <span className="hidden sm:inline">{SUPPORT_EMAIL}</span>
              <span className="sm:hidden">{t("footer.support")}</span>
            </a>
          </nav>
        </div>

        <p className="mt-3 border-t border-border/70 pt-3 text-center text-xs text-muted-foreground sm:text-left">
          © {year} {t("common.appName")}. {t("footer.rightsReserved")}
        </p>
      </div>
    </footer>
  )
}
