import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { SUPPORT_EMAIL } from "@/lib/brand"

/**
 * The end of the page, set as a colophon.
 *
 * Before this it was a 12px legal strip: brand, tagline, support address,
 * copyright, all on one line. Correct, and it read as the bottom of a form.
 *
 * Three mechanisms, all taken from places that do this well and all cheap:
 *
 * 1. **A hard tonal inversion**, not a tinted band. Anthropic's footer flips to
 *    near-black under an ivory page, and that inversion is what makes it read
 *    as a full stop rather than as more page. It costs one background colour.
 * 2. **One type size, hierarchy by colour.** Apple's footer is entirely 12px —
 *    section titles included — and sorts itself with three steps of opacity.
 *    Nothing is bolder or bigger; the eye is led by contrast alone.
 * 3. **No dividers.** The columns are held by the grid. Rules between footer
 *    columns are what a sitemap does; a colophon does not need them.
 *
 * The school's name is set in the serif at a size that means it — the one
 * place besides the masthead where the institution signs the page.
 */
export default function Footer() {
  const { t } = useTranslation()
  const year = new Date().getFullYear()

  const linkClass =
    "text-ink-inverted/60 transition-colors duration-200 hover:text-ink-inverted/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink-inverted/40 focus-visible:ring-offset-0 rounded-sm"

  return (
    <footer className="mt-auto bg-ink text-ink-inverted">
      <div className="container mx-auto max-w-[1400px] px-4 py-10 md:px-6 md:py-14">
        <div className="grid gap-8 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
          <div className="max-w-sm">
            <Link
              to="/"
              className="font-serif text-xl font-semibold tracking-[-0.01em] text-ink-inverted transition-opacity duration-200 hover:opacity-80 md:text-2xl"
            >
              {t("common.appName")}
            </Link>
            <p className="mt-2 text-sm leading-relaxed text-ink-inverted/60">
              {t("footer.tagline")}
            </p>
          </div>

          <div className="flex flex-col gap-1.5 text-sm sm:items-end">
            <a href={`mailto:${SUPPORT_EMAIL}`} className={linkClass}>
              {t("footer.support")}
            </a>
            {/* The year and the name, last and quietest — a colophon line, not
                a legal notice competing with the rest. */}
            <p className="text-ink-inverted/40">
              © {year} {t("common.appName")}
            </p>
          </div>
        </div>
      </div>
    </footer>
  )
}
