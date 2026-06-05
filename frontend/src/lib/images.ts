/**
 * Route Supabase Storage public URLs through a same-origin `/img/...` path.
 *
 * Why: AdBlock and privacy extensions (EasyList, Fanboy) match patterns like
 * `storage/v1/object/public/<bucket>/<uuid>/cover.jpg` and block the request,
 * even though it's our own content. Serving the same bytes from our own
 * domain via Vercel rewrite sidesteps those filters.
 *
 * In production (Vercel): `/img/:bucket/:path*` is rewritten to the Supabase
 * Storage public endpoint (see `frontend/vercel.json`).
 * In development (Vite): a dev proxy in `vite.config.ts` forwards the same
 * path to the Supabase project.
 */
const STORAGE_PUBLIC_PREFIX = "/storage/v1/object/public/"

let cachedSupabaseHost: string | null | undefined
function getSupabaseHost(): string | null {
  if (cachedSupabaseHost !== undefined) return cachedSupabaseHost
  const raw = import.meta.env.VITE_SUPABASE_URL
  if (!raw) {
    cachedSupabaseHost = null
    return null
  }
  try {
    cachedSupabaseHost = new URL(raw).host
  } catch {
    cachedSupabaseHost = null
  }
  return cachedSupabaseHost
}

export function toProxyImage(url: string | null | undefined): string | undefined {
  if (!url) return undefined
  if (url.startsWith("/img/")) return url
  try {
    const parsed = new URL(url, window.location.origin)
    // Defence-in-depth: only ever emit an http(s) URL into an <img src> /
    // CSS background. React already escapes JSX attributes, but rejecting
    // javascript:/data:/vbscript: here keeps dangerous schemes out of the
    // DOM entirely (and out of the HTML-rewrite path below).
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return undefined
    const supabaseHost = getSupabaseHost()
    if (!supabaseHost || parsed.host !== supabaseHost) return url
    if (!parsed.pathname.startsWith(STORAGE_PUBLIC_PREFIX)) return url
    const bucketAndPath = parsed.pathname.slice(STORAGE_PUBLIC_PREFIX.length)
    return `/img/${bucketAndPath}${parsed.search}`
  } catch {
    return url
  }
}

/** Rewrite `src` attributes on `<img>` tags inside an HTML string. */
export function rewriteHtmlImageSources(html: string): string {
  if (!html) return html
  return html.replace(
    /<img\b([^>]*?)\bsrc=(["'])([^"']+)\2/gi,
    (match, before: string, quote: string, src: string) => {
      const proxied = toProxyImage(src)
      if (!proxied || proxied === src) return match
      return `<img${before}src=${quote}${proxied}${quote}`
    },
  )
}
