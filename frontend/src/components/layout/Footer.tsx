import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { SUPPORT_EMAIL } from "@/lib/brand"

/**
 * Minimalist footer.
 *
 * Earlier revisions duplicated the header nav (Courses · Calendar ·
 * Certificates · Teacher · Admin) inside the footer. That doubled the
 * persistent surface area without giving the reader anything new — the
 * header already exposes every destination. The new shape keeps the
 * footer to its one job: brand mark, tagline, copyright, support
 * email. Anything else lives in the header.
 */
export default function Footer() {
  const { t } = useTranslation()
  const year = new Date().getFullYear()

  const linkClass =
    "text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-sm"

  return (
    <footer className="mt-auto border-t border-border bg-background/95">
      <div className="container mx-auto max-w-[1400px] px-4 py-5 md:px-6">
        <div className="flex flex-col items-start justify-between gap-3 text-xs sm:flex-row sm:items-center sm:gap-x-6 sm:text-sm">
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

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <a href={`mailto:${SUPPORT_EMAIL}`} className={linkClass}>
              {t("footer.support")}
            </a>
            <span aria-hidden className="text-muted-foreground/40">
              ·
            </span>
            <span>
              © {year} {t("common.appName")}
            </span>
          </div>
        </div>
      </div>
    </footer>
  )
}
