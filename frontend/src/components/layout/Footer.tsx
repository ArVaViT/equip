import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { SUPPORT_EMAIL } from "@/lib/brand"

import { BRAND_PATHS, type Brand } from "./brandIcons"

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
 * SOCIAL AND APPS, NOT YET LIVE (2026-09-27). Above the legal line, at the
 * same colour and smaller still: six social marks and the two stores, on
 * Vadym's word — «пусть они будут неактивны, но будут … очень мелкими».
 * They are not links, because there is nothing to link to; a link that goes
 * nowhere is a broken link. They say so once, with «Soon», and to a screen
 * reader through the group labels. The stores are plain pills in the
 * footer's own type, not Apple's and Google's badges: both companies'
 * guidelines allow those only as links to a published app.
 *
 * It renders from `PublicLanding` and nowhere else. The application shell has
 * no footer at all — see the note in `App.tsx`.
 */
export default function Footer({ className = "mt-6" }: { className?: string }) {
  const { t } = useTranslation()
  const year = new Date().getFullYear()

  const linkClass =
    "whitespace-nowrap rounded-sm transition-colors duration-fast ease-out hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"

  return (
    <footer className={className}>
      <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-3 px-4 pt-6 text-ink-muted">
        <ul aria-label={t("footer.social")} className="flex items-center gap-3.5">
          {SOCIAL.map((brand) => (
            <li key={brand} title={`${brand} · ${t("footer.soon")}`}>
              <Glyph brand={brand} className="h-3 w-3" />
            </li>
          ))}
        </ul>
        <span aria-hidden className="h-3 w-px bg-line" />
        <ul aria-label={t("footer.apps")} className="flex items-center gap-2">
          {STORES.map(({ brand, name }) => (
            <li
              key={brand}
              title={`${name} · ${t("footer.soon")}`}
              className="flex items-center gap-1 rounded-md border border-line px-2 py-1 text-[0.625rem] leading-none"
            >
              <Glyph brand={brand} className="h-2.5 w-2.5" />
              {name}
            </li>
          ))}
          <li className="text-[0.625rem] uppercase tracking-wider">{t("footer.soon")}</li>
        </ul>
      </div>
      <nav
        aria-label={t("footer.legal")}
        className="mx-auto flex flex-wrap items-baseline justify-center gap-x-2.5 gap-y-2 px-4 pb-6 pt-4 text-[0.6875rem] text-ink-muted lg:flex-nowrap xl:gap-x-4 xl:px-6"
      >
        <span className="whitespace-nowrap">© {year}</span>
        {/* The one link here that is not a legal page: the showcase of who
            teaches on Equip had no way in from the public page (2026-10-03). */}
        <Link to="/organizations" className={linkClass}>
          {t("footer.organizations")}
        </Link>
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

const SOCIAL: Brand[] = ["YouTube", "Instagram", "Telegram", "Facebook", "TikTok", "WhatsApp"]
const STORES: { brand: Brand; name: string }[] = [
  { brand: "Apple", name: "App Store" },
  { brand: "GooglePlay", name: "Google Play" },
]

function Glyph({ brand, className }: { brand: Brand; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} role="img" aria-label={brand}>
      <path d={BRAND_PATHS[brand]} />
    </svg>
  )
}
