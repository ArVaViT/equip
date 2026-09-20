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

  // Half the height it used to be. The footer is small print and a few
  // links; at `mt-24` over `py-16` it took most of a screen on the one page
  // it appears on, directly after a hero built to be looked at.
  return (
    <footer className="mt-16 border-t border-edge">
      <div className="container mx-auto max-w-5xl px-4 py-8">
        {/* One row, not three columns.
            The column layout stacked a tagline, a "Продукт" heading over
            three links and a "Документы" heading over six, which came to
            387px — a third of a screen of small print directly after a hero
            built to be looked at, and Vadym read it as not having been
            shrunk at all, because in the part he could see it had not been.
            The links are the same links; headings a reader does not need in
            order to recognise "Политика конфиденциальности" are gone, and
            the row wraps instead of stacking. */}
        <div className="flex flex-col gap-6 sm:flex-row sm:items-baseline sm:justify-between">
          <div className="max-w-xs">
            <Link
              to="/"
              className="font-serif text-xl font-semibold tracking-[-0.02em] text-ink transition-opacity duration-fast hover:opacity-70"
            >
              {t("common.appName")}
            </Link>
            {/* Kept, and kept small. `Footer.test.tsx` pins it, and rightly:
                it is the only place on a page a crawler reads that says in
                one line what this is. */}
            <p className="mt-2 text-sm leading-relaxed text-ink-muted">{t("footer.tagline")}</p>
          </div>

          {/* Only destinations a signed-out visitor can actually reach.
              `/calendar` and `/certificates` are behind `Gate mode="private"`,
              so putting them here would send a stranger who is reading the
              marketing page straight into a login wall.
              `/dmca` stays: § 512(i)(1)(A) asks a platform to *inform* people
              of its repeat-infringer policy, and a page nobody can find from
              the site does not inform anybody. */}
          <nav aria-label={t("footer.product")}>
            <ul className="flex flex-wrap gap-x-5 gap-y-2.5 text-sm sm:justify-end">
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
                <Link to="/dmca" className={linkClass}>
                  {t("dmca.title")}
                </Link>
              </li>
              <li>
                <Link to="/teacher-terms" className={linkClass}>
                  {t("legal.teacherTerms")}
                </Link>
              </li>
              <li>
                <Link to="/school-agreement" className={linkClass}>
                  {t("legal.schoolAgreement")}
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
        <p className="mt-6 border-t border-edge pt-4 text-xs text-ink-muted">
          © {year} {t("common.appName")}
        </p>
      </div>
    </footer>
  )
}
