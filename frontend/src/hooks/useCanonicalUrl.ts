import { useEffect } from "react"
import { useLocation } from "react-router-dom"
import { useTranslation } from "react-i18next"

export const SITE_ORIGIN = "https://equipbible.com"

/**
 * The pages that are each their own document for a search engine — the same
 * set the sitemap lists (`scripts/build-sitemap.mjs`, STATIC_PAGES plus one
 * page per course and per organization). `__tests__/useCanonicalUrl.test.ts`
 * holds the two lists together.
 */
export const CANONICAL_STATIC_PATHS = [
  "/",
  "/courses",
  "/organizations",
  "/verify",
  "/privacy",
  "/privacy/providers",
  "/terms",
  "/teacher-terms",
  "/school-agreement",
  "/dmca",
] as const

const COURSE_RE = /^\/courses\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const ORGANIZATION_RE = /^\/o\/[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?$/

/** The canonical URL for `pathname`, or null for a page that is not one. */
export function canonicalUrlFor(pathname: string): string | null {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname
  if ((CANONICAL_STATIC_PATHS as readonly string[]).includes(path)) return SITE_ORIGIN + path
  if (COURSE_RE.test(path)) return SITE_ORIGIN + path.toLowerCase()
  if (ORGANIZATION_RE.test(path)) return SITE_ORIGIN + path
  return null
}

function setLink(rel: string, href: string | null) {
  let el = document.head.querySelector<HTMLLinkElement>(`link[rel="${rel}"]`)
  if (!href) {
    el?.remove()
    return
  }
  if (!el) {
    el = document.createElement("link")
    el.rel = rel
    document.head.appendChild(el)
  }
  if (el.href !== href) el.href = href
}

function setMetaProperty(property: string, content: string | null) {
  const el = document.head.querySelector<HTMLMetaElement>(`meta[property="${property}"]`)
  if (el && content) el.content = content
}

/**
 * Keep `<link rel="canonical">` naming the page on screen.
 *
 * `index.html` ships one canonical, `/`, and the server answers every address
 * with that file — so before this, a course page rendered in the browser
 * declared itself a copy of the home page. Each public page now names itself;
 * every other page (a dashboard, a lesson, a 404) carries no canonical at all
 * rather than a wrong one.
 *
 * A page prerendered at build time (`scripts/prerender-pages.mjs`) arrives
 * with its own description and a schema.org block in the head. Those are true
 * only of that page, so once the reader navigates elsewhere in the app they go,
 * and the description returns to the site's own.
 */
export function useCanonicalUrl() {
  const { pathname } = useLocation()
  const { t } = useTranslation()

  useEffect(() => {
    const canonical = canonicalUrlFor(pathname)
    setLink("canonical", canonical)
    setMetaProperty("og:url", canonical ?? `${SITE_ORIGIN}/`)

    const root = document.documentElement
    const prerendered = root.getAttribute("data-prerendered")
    if (prerendered && prerendered !== pathname.replace(/\/+$/, "")) {
      root.removeAttribute("data-prerendered")
      for (const el of document.head.querySelectorAll("[data-prerender]")) el.remove()
      document.head
        .querySelector<HTMLMetaElement>('meta[name="description"]')
        ?.setAttribute("content", t("meta.description"))
    }
  }, [pathname, t])
}
