import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { SUPPORT_EMAIL } from "@/lib/brand"

/**
 * The end of the public page — and only the public page.
 *
 * Two corrections here, both from being told the previous version was worse
 * and then going to measure instead of arguing.
 *
 * **It is not inverted.** The last one flipped to a hard tonal block, on the
 * theory that inversion reads as a full stop. Linear's footer is
 * `rgb(8,9,10)` — the same value as their page — separated by a single 1px
 * border. Vercel's marketing footer does the same. An inverted slab under a
 * page is what a 2013 site does to announce "the content is over"; a hairline
 * does the same job without dropping a brick on the layout.
 *
 * **It has structure.** The last one was a serif wordmark, a tagline and a
 * right-aligned column of four links — a magazine colophon, which is exactly
 * the register that reads as old. Linear's footer has six columns and
 * forty-three links under 13px headings. We do not have forty-three links,
 * but we do have two distinct kinds, and saying so in two labelled columns is
 * the difference between a footer and a leftover.
 *
 * It renders from `PublicLanding` and nowhere else. The application shell has
 * no footer at all — see the note in `App.tsx`.
 */
export default function Footer() {
  const { t } = useTranslation()
  const year = new Date().getFullYear()

  const linkClass =
    "rounded-sm text-ink-muted transition-colors duration-fast ease-out hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
  const headingClass = "text-xs font-medium uppercase tracking-[0.14em] text-ink"

  return (
    <footer className="mt-24 border-t border-edge">
      <div className="container mx-auto max-w-5xl px-4 py-14 md:py-16">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]">
          <div className="max-w-xs">
            <Link
              to="/"
              className="font-serif text-xl font-semibold tracking-[-0.02em] text-ink transition-opacity duration-fast hover:opacity-70"
            >
              {t("common.appName")}
            </Link>
            <p className="mt-3 text-sm leading-relaxed text-ink-muted">{t("footer.tagline")}</p>
          </div>

          <nav aria-labelledby="footer-product">
            <p id="footer-product" className={headingClass}>
              {t("footer.product")}
            </p>
            {/* Only destinations a signed-out visitor can actually reach.
                `/calendar` and `/certificates` are behind `Gate mode="private"`,
                so putting them here would send a stranger who is reading the
                marketing page straight into a login wall. */}
            <ul className="mt-4 space-y-2.5 text-sm">
              <li>
                <Link to="/courses" className={linkClass}>
                  {t("header.courses")}
                </Link>
              </li>
              <li>
                <Link to="/register" className={linkClass}>
                  {t("common.register")}
                </Link>
              </li>
              <li>
                <Link to="/login" className={linkClass}>
                  {t("common.signIn")}
                </Link>
              </li>
            </ul>
          </nav>

          <nav aria-labelledby="footer-legal">
            <p id="footer-legal" className={headingClass}>
              {t("footer.legal")}
            </p>
            <ul className="mt-4 space-y-2.5 text-sm">
              <li>
                <Link to="/privacy" className={linkClass}>
                  {t("legal.privacy")}
                </Link>
              </li>
              <li>
                <Link to="/terms" className={linkClass}>
                  {t("legal.terms")}
                </Link>
              </li>
              <li>
                <a href={`mailto:${SUPPORT_EMAIL}`} className={linkClass}>
                  {t("footer.support")}
                </a>
              </li>
            </ul>
          </nav>
        </div>

        {/* The colophon line, last and smallest. It is the only thing here
            that is not a way of getting somewhere. */}
        <p className="mt-12 border-t border-edge pt-6 text-xs text-ink-muted">
          © {year} {t("common.appName")}
        </p>
      </div>
    </footer>
  )
}
