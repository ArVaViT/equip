/**
 * Give each public page its own `<head>` in the HTML the server sends.
 *
 * The app is a single-page app: every address is answered with the same
 * `dist/index.html`, and React fills the page in afterwards. A crawler that
 * reads the raw response — Bing, the AI-search fetchers, every link unfurler —
 * therefore saw the landing page's title, description and share card on a
 * course page, and a `<link rel="canonical">` pointing at `/`: a claim that
 * every course page is a copy of the home page, which is the one thing a
 * search engine should not be told about the pages it most needs to index.
 *
 * So, after `vite build`, this writes a copy of `dist/index.html` per page:
 *
 *  - `dist/courses/<id>/index.html` for each public course, with the course's
 *    own title, description, canonical URL, share card and a schema.org
 *    `Course` block — all of it taken from `GET /api/v1/courses`, nothing
 *    invented. `<html data-prerendered>` tells `/locale-boot.js` not to put
 *    the generic title back over it.
 *  - `dist/<path>/index.html` for the other static public pages (catalogue,
 *    /verify, the legal documents), changing only the canonical URL and
 *    `og:url`: the title there is the interface's, set per language.
 *
 * Vercel serves a file from the build output before it applies any rewrite,
 * so these copies win over the SPA fallback without touching `vercel.json`;
 * `/courses/<id>` and `/courses/<id>/` both resolve to the directory's
 * `index.html`. The bundle in each copy is the same bundle — React mounts over
 * it exactly as it does over `index.html` (this is not SSR; `#root` is empty).
 *
 * Driven by `build-sitemap.mjs`, which already fetches the catalogue: one
 * request feeds both. When the catalogue cannot be read the course pages are
 * simply not written and the SPA fallback answers them, as before.
 */

import { mkdirSync, writeFileSync } from "node:fs"
import { dirname, resolve } from "node:path"

export const SITE_ORIGIN = "https://equipbible.com"
export const DESCRIPTION_MAX = 155

function escapeHtml(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
}

/**
 * JSON for a `<script type="application/ld+json">` block. `<` is escaped so a
 * course description containing `</script>` cannot close the block early.
 */
function jsonLd(value) {
  return JSON.stringify(value, null, 2).replace(/</g, "\\u003c")
}

/** Plain text of a description: no markup, whitespace collapsed. */
export function plainText(value) {
  if (typeof value !== "string") return ""
  return value
    .replace(/<[^>]*>/g, " ")
    .replace(/[*_`#>]+/g, "")
    .replace(/\s+/g, " ")
    .trim()
}

/** Cut to `max` characters at a word boundary, with an ellipsis if cut. */
export function truncate(text, max = DESCRIPTION_MAX) {
  if (text.length <= max) return text
  const cut = text.slice(0, max - 1)
  const space = cut.lastIndexOf(" ")
  return `${(space > max * 0.6 ? cut.slice(0, space) : cut).replace(/[\s,.;:—–-]+$/, "")}…`
}

/** An absolute URL for an image the API returned, or null. */
export function absoluteImage(url) {
  if (typeof url !== "string" || !url) return null
  if (url.startsWith("/") && !url.startsWith("//")) return SITE_ORIGIN + url
  if (/^https:\/\//.test(url)) return url
  return null
}

/**
 * Replace exactly one tag matched by `pattern` in `html`. Throws when the
 * template no longer has it, so a change to index.html cannot silently produce
 * pages that carry the home page's head.
 */
function replaceOne(html, pattern, replacement, label) {
  const matches = html.match(new RegExp(pattern.source, "g")) ?? []
  if (matches.length !== 1) throw new Error(`index.html: expected one ${label}, found ${matches.length}`)
  return html.replace(pattern, replacement)
}

function setMeta(html, attr, key, content) {
  const pattern = new RegExp(`<meta ${attr}="${key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}" content="[^"]*" />`)
  return replaceOne(html, pattern, `<meta ${attr}="${key}" content="${escapeHtml(content)}" />`, `${attr}=${key}`)
}

function dropMeta(html, attr, key) {
  return html.replace(new RegExp(`\\s*<meta ${attr}="${key}" content="[^"]*" />`), "")
}

/** Point the canonical link and og:url at `path`. */
export function withCanonical(template, path) {
  const url = SITE_ORIGIN + path
  let html = replaceOne(
    template,
    /<link rel="canonical" href="[^"]*" \/>/,
    `<link rel="canonical" href="${escapeHtml(url)}" />`,
    "canonical link",
  )
  html = setMeta(html, "property", "og:url", url)
  return html
}

/**
 * The page fields for one course from the catalogue, or null when the course
 * has nothing to say in the language fetched (an untranslated title is `""`).
 */
export function coursePageData(course) {
  const title = typeof course?.title === "string" ? course.title.trim() : ""
  if (!title) return null
  const fullDescription = plainText(course.description)
  return {
    id: course.id.toLowerCase(),
    title,
    description: truncate(fullDescription || title),
    fullDescription,
    image: absoluteImage(course.image_url),
    // The catalogue's own promise (FAQ: "Every course in the catalogue is free
    // to take"); `public` is the access mode a stranger can enrol in alone.
    free: course.access_mode === "public",
    organizationName: typeof course.organization_name === "string" ? course.organization_name : null,
    updatedAt: typeof course.updated_at === "string" ? course.updated_at : null,
  }
}

/** schema.org Course for one course — only fields the API gave us. */
export function courseJsonLd(page, inLanguage) {
  const url = `${SITE_ORIGIN}/courses/${page.id}`
  const course = {
    "@context": "https://schema.org",
    "@type": "Course",
    "@id": `${url}#course`,
    name: page.title,
    description: page.fullDescription || page.title,
    url,
    inLanguage,
    provider: { "@type": "Organization", "@id": `${SITE_ORIGIN}/#organization`, name: "Equip", url: `${SITE_ORIGIN}/` },
  }
  if (page.image) course.image = page.image
  if (page.free) course.isAccessibleForFree = true
  if (page.updatedAt) course.dateModified = page.updatedAt
  return course
}

/** `dist/index.html` rewritten for one course. */
export function renderCoursePage(template, page, { inLanguage = "en" } = {}) {
  const path = `/courses/${page.id}`
  const title = `${page.title} — Equip`
  let html = withCanonical(template, path)
  html = replaceOne(html, /<html lang="[^"]*"/, `<html lang="${inLanguage}" data-prerendered="${path}"`, "<html>")
  html = replaceOne(html, /<title>[^<]*<\/title>/, `<title>${escapeHtml(title)}</title>`, "<title>")
  html = setMeta(html, "name", "description", page.description)
  html = setMeta(html, "property", "og:title", title)
  html = setMeta(html, "property", "og:description", page.description)
  html = setMeta(html, "name", "twitter:title", title)
  html = setMeta(html, "name", "twitter:description", page.description)
  // A course page is not the website; Open Graph has no "course" type, and
  // `article` would claim an author and a publication date it does not have.
  html = setMeta(html, "property", "og:type", "website")
  if (page.image) {
    html = setMeta(html, "property", "og:image", page.image)
    html = setMeta(html, "name", "twitter:image", page.image)
    html = setMeta(html, "property", "og:image:alt", page.title)
    // The site card's 1200×630 does not describe a teacher's cover.
    html = dropMeta(html, "property", "og:image:width")
    html = dropMeta(html, "property", "og:image:height")
  }
  const block = `    <script type="application/ld+json" data-prerender>\n${jsonLd(courseJsonLd(page, inLanguage))}\n    </script>\n  </head>`
  html = replaceOne(html, /\s*<\/head>/, `\n${block}`, "</head>")
  return html
}

/**
 * Write the per-page copies into `distDir`. Returns how many of each were
 * written. Throws only on a template that no longer has the tags it edits;
 * the caller logs that and leaves the SPA fallback in charge.
 */
export function writePrerenderedPages({ distDir, template, staticPaths, courses, inLanguage = "en" }) {
  const writeAt = (path, html) => {
    const file = resolve(distDir, `.${path}`, "index.html")
    mkdirSync(dirname(file), { recursive: true })
    writeFileSync(file, html)
  }
  let staticCount = 0
  for (const path of staticPaths) {
    if (path === "/") continue // dist/index.html already is that page.
    writeAt(path, withCanonical(template, path))
    staticCount++
  }
  let courseCount = 0
  for (const course of courses) {
    const page = coursePageData(course)
    if (!page) continue
    writeAt(`/courses/${page.id}`, renderCoursePage(template, page, { inLanguage }))
    courseCount++
  }
  return { staticCount, courseCount }
}
