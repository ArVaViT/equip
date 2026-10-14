/**
 * Write `dist/sitemap.xml` — the static public pages plus every public course.
 *
 * Runs after `vite build`. Vite has already copied `public/sitemap.xml` into
 * `dist/`, and that committed file is the fallback: the static pages only. This
 * script then asks the production API for the catalogue a stranger sees
 * (`GET /api/v1/courses` — published, `access_mode = public`; the backend owns
 * that rule) and for the organization showcase (`GET /api/v1/organizations`),
 * and overwrites `dist/sitemap.xml` with the static pages plus `/courses/<id>`
 * and `/o/<slug>` for each.
 *
 * It never fails the build. No network, a timeout, a 5xx, a shape it does not
 * recognise — it says so on stderr and leaves the static copy in place. A
 * sitemap missing the courses for one deploy costs nothing; a deploy that
 * cannot ship because the API blinked costs a great deal.
 *
 * Why the production API even for a preview build: the sitemap describes
 * equipbible.com, and only production's catalogue is the one at those URLs.
 * `SITEMAP_API_URL` overrides it; `SITEMAP_SKIP_FETCH=1` skips the fetch.
 *
 * Every URL is checked against `public/robots.txt` before it is written, so a
 * route closed there can never be advertised here. Google Search Console
 * reported exactly that mismatch's cousin on 2026-10-13: `/login`,
 * `/register` and `/forgot-password` were listed — forms with nothing to
 * find — while no single course was.
 */

import { existsSync, readFileSync, writeFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const here = dirname(fileURLToPath(import.meta.url))
const publicDir = resolve(here, "../public")
const distDir = resolve(here, "../dist")

export const SITE_ORIGIN = "https://equipbible.com"
export const DEFAULT_API_ORIGIN = "https://api.equipbible.com"
export const FETCH_TIMEOUT_MS = 10_000

/**
 * The public pages that are worth finding by search. Not the sign-in and
 * sign-up forms or the password reset — robots.txt closes those. `/verify`
 * stays: every certificate prints a number that points there, and the
 * stranger checking it has to be able to find it (see crawlableSurface.test).
 *
 * `public/sitemap.xml` is this list rendered; `__tests__/sitemap.test.ts`
 * fails if the two drift.
 */
export const STATIC_PAGES = [
  { path: "/", changefreq: "weekly", priority: "1.0" },
  { path: "/courses", changefreq: "daily", priority: "0.9" },
  { path: "/organizations", changefreq: "weekly", priority: "0.7" },
  { path: "/verify", changefreq: "monthly", priority: "0.6" },
  { path: "/privacy", changefreq: "yearly", priority: "0.4" },
  { path: "/privacy/providers", changefreq: "monthly", priority: "0.3" },
  { path: "/terms", changefreq: "yearly", priority: "0.4" },
  { path: "/teacher-terms", changefreq: "yearly", priority: "0.4" },
  { path: "/school-agreement", changefreq: "yearly", priority: "0.4" },
  { path: "/dmca", changefreq: "yearly", priority: "0.4" },
]

// Course ids are UUIDs; organization slugs are lowercase words and hyphens.
// Anything else in a response is not something this script knows how to
// put in a URL, and is dropped rather than escaped into one.
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const SLUG_RE = /^[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?$/

/** Parse the `User-agent: *` group of a robots.txt into Allow/Disallow rules. */
export function parseRobots(text) {
  const rules = []
  let inStarGroup = false
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.replace(/#.*/, "").trim()
    if (!line) continue
    const idx = line.indexOf(":")
    if (idx < 0) continue
    const field = line.slice(0, idx).trim().toLowerCase()
    const value = line.slice(idx + 1).trim()
    if (field === "user-agent") {
      inStarGroup = value === "*"
    } else if (inStarGroup && (field === "allow" || field === "disallow") && value) {
      rules.push({ allow: field === "allow", prefix: value })
    }
  }
  return rules
}

/**
 * Google's reading: the longest matching prefix wins, and Allow wins a tie.
 * No wildcards — robots.txt here does not use them.
 */
export function isAllowed(path, rules) {
  let best = null
  for (const rule of rules) {
    if (!path.startsWith(rule.prefix)) continue
    if (
      !best ||
      rule.prefix.length > best.prefix.length ||
      (rule.prefix.length === best.prefix.length && rule.allow)
    ) {
      best = rule
    }
  }
  return best ? best.allow : true
}

function escapeXml(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;")
}

/** `YYYY-MM-DD` from an ISO timestamp, or null when it is not one. */
function toLastmod(value) {
  if (typeof value !== "string") return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d.toISOString().slice(0, 10)
}

/** Course entries from the catalogue response; ignores anything malformed. */
export function courseEntries(courses) {
  if (!Array.isArray(courses)) throw new Error("courses response is not an array")
  const seen = new Set()
  const out = []
  for (const c of courses) {
    if (!c || typeof c.id !== "string" || !UUID_RE.test(c.id)) continue
    // The endpoint already filters to these; checked again so a backend
    // change that widened it could not quietly publish a draft's URL.
    if (c.status !== undefined && c.status !== "published") continue
    if (c.access_mode !== undefined && c.access_mode !== "public") continue
    if (c.deleted_at) continue
    const id = c.id.toLowerCase()
    if (seen.has(id)) continue
    seen.add(id)
    out.push({ path: `/courses/${id}`, lastmod: toLastmod(c.updated_at), changefreq: "weekly", priority: "0.8" })
  }
  return out
}

/** Organization page entries from the showcase response. */
export function organizationEntries(orgs) {
  if (!Array.isArray(orgs)) throw new Error("organizations response is not an array")
  const seen = new Set()
  const out = []
  for (const o of orgs) {
    if (!o || typeof o.slug !== "string" || !SLUG_RE.test(o.slug) || seen.has(o.slug)) continue
    seen.add(o.slug)
    out.push({ path: `/o/${o.slug}`, lastmod: null, changefreq: "weekly", priority: "0.6" })
  }
  return out
}

/** Render entries as a sitemap, dropping anything robots.txt disallows. */
export function renderSitemap(entries, robotsRules) {
  const seen = new Set()
  const urls = []
  for (const e of entries) {
    if (seen.has(e.path) || !isAllowed(e.path, robotsRules)) continue
    seen.add(e.path)
    const lines = ["  <url>", `    <loc>${escapeXml(SITE_ORIGIN + e.path)}</loc>`]
    if (e.lastmod) lines.push(`    <lastmod>${e.lastmod}</lastmod>`)
    lines.push(`    <changefreq>${e.changefreq}</changefreq>`, `    <priority>${e.priority}</priority>`, "  </url>")
    urls.push(lines.join("\n"))
  }
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    "<!--",
    "  Generated by frontend/scripts/build-sitemap.mjs. This committed copy is",
    "  the static fallback; the build overwrites dist/sitemap.xml with the same",
    "  pages plus every public course and organization page.",
    "-->",
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ...urls,
    "</urlset>",
    "",
  ].join("\n")
}

async function fetchJson(url, fetchImpl) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)
  try {
    const res = await fetchImpl(url, { headers: { Accept: "application/json" }, signal: controller.signal })
    if (!res.ok) throw new Error(`${url} answered ${res.status}`)
    return await res.json()
  } finally {
    clearTimeout(timer)
  }
}

/**
 * The full sitemap, or null when the dynamic part could not be built. Courses
 * are required; the organization showcase is best-effort on its own.
 */
export async function buildDynamicSitemap({ apiOrigin, robotsRules, fetchImpl = fetch, log = console.warn }) {
  const base = apiOrigin.replace(/\/+$/, "")
  let courses
  try {
    courses = courseEntries(await fetchJson(`${base}/api/v1/courses?limit=200`, fetchImpl))
  } catch (err) {
    log(`[sitemap] courses unavailable, keeping the static sitemap: ${err instanceof Error ? err.message : err}`)
    return null
  }
  let orgs = []
  try {
    orgs = organizationEntries(await fetchJson(`${base}/api/v1/organizations?limit=200`, fetchImpl))
  } catch (err) {
    log(`[sitemap] organizations unavailable, listing courses only: ${err instanceof Error ? err.message : err}`)
  }
  return { xml: renderSitemap([...STATIC_PAGES, ...courses, ...orgs], robotsRules), courses: courses.length, orgs: orgs.length }
}

export function readRobotsRules() {
  return parseRobots(readFileSync(resolve(publicDir, "robots.txt"), "utf8"))
}

async function main() {
  const outFile = resolve(distDir, "sitemap.xml")
  if (!existsSync(distDir)) {
    console.warn("[sitemap] dist/ does not exist; run after `vite build`. Skipping.")
    return
  }
  if (process.env.SITEMAP_SKIP_FETCH === "1") {
    console.log("[sitemap] SITEMAP_SKIP_FETCH=1, keeping the static sitemap.")
    return
  }
  const robotsRules = readRobotsRules()
  const apiOrigin = process.env.SITEMAP_API_URL || DEFAULT_API_ORIGIN
  const result = await buildDynamicSitemap({ apiOrigin, robotsRules })
  if (!result) return
  writeFileSync(outFile, result.xml)
  console.log(
    `[sitemap] dist/sitemap.xml: ${STATIC_PAGES.length} static pages, ${result.courses} courses, ${result.orgs} organizations.`,
  )
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  // Never let this script fail the build.
  main().catch((err) => {
    console.warn(`[sitemap] unexpected error, keeping the static sitemap: ${err instanceof Error ? err.message : err}`)
  })
}
