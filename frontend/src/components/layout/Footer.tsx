import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { SUPPORT_EMAIL } from "@/lib/brand"

/**
 * The end of the public page — and only the public page.
 *
 * One line of small print, and nothing a reader has to look at.
 *
 * It has been shrunk three times, and each round removed a different kind
 * of weight. First the inverted slab went (an inverted block under a page is
 * what a 2013 site does to say "the content is over"). Then the two
 * labelled columns went, 387px down to 109px. Then, on 2026-09-23, the last
 * two things that made it a *section* rather than a margin: the rule across
 * the top and the wordmark. Vadym: «убери линию которая делит футер, она не
 * нужна … однострочным и без названия, оно занимает много места, я хочу
 * его невзрачным».
 *
 * Why those two. The rule drew a border around nine links, which announced
 * them as a region worth a reader's attention; without it they are simply
 * the bottom of the page. The name is already in the header, the tab title
 * and the h1's neighbourhood — here it was a 20px serif mark sitting at the
 * same size as the course titles on the shelf above it.
 *
 * ONE LINE IN EVERY LANGUAGE. The courses / register / sign-in links are
 * gone because the header carries all three on every screen, and they were
 * what pushed the German row onto a second line. What remains is the
 * copyright and the legal pages at 11px, with `nowrap` on each item so that
 * if a narrow window does wrap it breaks between links, never inside
 * «Teacher & Contributor Agreement». The size is not a taste call: at 12px
 * the Russian row («Жалобы на нарушение авторских прав», «Связаться с
 * поддержкой») measured 1098px and overflowed a 1024px window; at 11px
 * with 10px gaps (16px from `xl`) every language fits from `lg` up, where
 * `flex-nowrap` holds it. Below `lg` it wraps — six legal titles do not fit
 * across a phone in any language, and a sideways scrolling footer is worse
 * than a two-line one.
 *
 * It renders from `PublicLanding` and nowhere else. The application shell has
 * no footer at all — see the note in `App.tsx`.
 */
export default function Footer() {
  const { t } = useTranslation()
  const year = new Date().getFullYear()

  const linkClass =
    "whitespace-nowrap rounded-sm transition-colors duration-fast ease-out hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"

  return (
    <footer className="mt-6">
      <nav
        aria-label={t("footer.legal")}
        className="mx-auto flex flex-wrap items-baseline justify-center gap-x-2.5 gap-y-2 px-4 py-6 text-[0.6875rem] text-ink-muted lg:flex-nowrap xl:gap-x-4 xl:px-6"
      >
        <span className="whitespace-nowrap">© {year}</span>
        <Link to="/privacy" className={linkClass}>
          {t("legal.privacy")}
        </Link>
        <Link to="/terms" className={linkClass}>
          {t("legal.terms")}
        </Link>
        <Link to="/dmca" className={linkClass}>
          {t("dmca.title")}
        </Link>
        <Link to="/teacher-terms" className={linkClass}>
          {t("legal.teacherTerms")}
        </Link>
        <Link to="/school-agreement" className={linkClass}>
          {t("legal.schoolAgreement")}
        </Link>
        <a href={`mailto:${SUPPORT_EMAIL}`} className={linkClass}>
          {t("footer.support")}
        </a>
      </nav>
    </footer>
  )
}
