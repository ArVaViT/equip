import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { readdirSync } from 'fs'

// VERCEL_GIT_COMMIT_SHA is injected by Vercel at build time. Falls back to
// 'dev' for local builds so Datadog RUM can still tag events with a version.
const appVersion =
  process.env.VITE_APP_VERSION ||
  (process.env.VERCEL_GIT_COMMIT_SHA ? process.env.VERCEL_GIT_COMMIT_SHA.slice(0, 7) : 'dev')

// WebMCP origin trial (lib/webmcp.ts). The token is the owner's to register
// and lives in the environment, never in the repo; without it no tag is
// written. An origin-trial token is meant to be public — it is bound to the
// origin — but it expires, and a stale one in git would be dead markup.
function webMcpOriginTrial(): Plugin {
  let token = ''
  return {
    name: 'equip-webmcp-origin-trial',
    configResolved(config) {
      token = (config.env.VITE_WEBMCP_OT_TOKEN ?? process.env.VITE_WEBMCP_OT_TOKEN ?? '').trim()
    },
    transformIndexHtml() {
      if (!/^[A-Za-z0-9+/=]+$/.test(token)) return []
      return [{ tag: 'meta', attrs: { 'http-equiv': 'origin-trial', content: token }, injectTo: 'head' }]
    },
  }
}

// A preconnect to the API origin, written into index.html at build time.
// The API is a different origin (api.equipbible.com) and nothing in the HTML
// names it, so its DNS, TCP and TLS handshakes used to start only when the
// first page asked for data — after the bundle, the locale catalog and the
// first render. On a phone that is three round trips added to the course
// page's largest paint, which is text the API returns. `crossorigin`: the
// requests are CORS without cookies, which use the anonymous connection pool.
// Same-origin or unset (a local build against a proxy): nothing to warm.
function apiPreconnect(): Plugin {
  let origin = ''
  return {
    name: 'equip-api-preconnect',
    configResolved(config) {
      const raw = (config.env.VITE_API_URL ?? process.env.VITE_API_URL ?? '').trim()
      try {
        const url = new URL(raw)
        origin = url.protocol === 'https:' ? url.origin : ''
      } catch {
        origin = ''
      }
    },
    transformIndexHtml() {
      if (!origin) return []
      return [{ tag: 'link', attrs: { rel: 'preconnect', href: origin, crossorigin: true }, injectTo: 'head' }]
    },
  }
}

// The hashed URL of each locale catalog, written onto the
// `<script src="/locale-boot.js">` tag so that script can preload the one it
// picks (see scripts/build-locale-boot.mjs). Build only: the dev server
// serves catalogs as modules, and the boot script does nothing without the
// attribute. The tag is matched exactly and the build fails if it is not
// there, so a rename of index.html cannot drop the preload in silence.
const LOCALE_BOOT_TAG = '<script src="/locale-boot.js"></script>'
function localeCatalogPreload(): Plugin {
  return {
    name: 'equip-locale-catalog-preload',
    apply: 'build',
    transformIndexHtml: {
      order: 'post',
      handler(html, ctx) {
        const locales = readdirSync(path.resolve(import.meta.dirname, 'src/i18n/locales'))
          .filter((f) => f.endsWith('.json'))
          .map((f) => f.slice(0, -'.json'.length))
        const catalogs: Record<string, string> = {}
        for (const file of Object.keys(ctx.bundle ?? {})) {
          const match = /^assets\/([a-z]+)-[A-Za-z0-9_-]{8}\.json$/.exec(file)
          if (match?.[1] && locales.includes(match[1])) catalogs[match[1]] = `/${file}`
        }
        if (Object.keys(catalogs).length !== locales.length) {
          throw new Error(`locale catalogs: expected ${locales.join(', ')}, found ${JSON.stringify(catalogs)}`)
        }
        if (!html.includes(LOCALE_BOOT_TAG)) throw new Error(`index.html: ${LOCALE_BOOT_TAG} not found`)
        return html.replace(
          LOCALE_BOOT_TAG,
          `<script src="/locale-boot.js" data-catalogs='${JSON.stringify(catalogs)}'></script>`,
        )
      },
    },
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), webMcpOriginTrial(), apiPreconnect(), localeCatalogPreload()],
  define: {
    'import.meta.env.VITE_APP_VERSION': JSON.stringify(appVersion),
  },
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  build: {
    // 'hidden' generates .map files alongside bundles but omits the
    // //# sourceMappingURL trailer, so browsers don't auto-fetch them.
    // Datadog RUM still resolves them server-side after upload via
    // datadog-ci in the postbuild step.
    sourcemap: 'hidden',
    rollupOptions: {
      output: {
        // Keep only the chunks that genuinely benefit from manual splitting:
        // the React runtime (shared by every route), the Supabase client
        // (loaded eagerly by AuthContext) and motion. The previous `ui` bucket
        // forced a handful of ~2KB utility libs into a separate request for
        // every visitor, and `editor` duplicated the automatic async chunk
        // that already gets created when `RichTextEditor` is dynamically
        // imported from the lazy teacher routes (CourseEditor / ChapterEditor).
        //
        // `codeSplitting` groups, not `manualChunks`: under Rolldown the
        // function form is deprecated, and it put a group's dependencies in
        // whichever group claimed them first. Motion imports React, so React
        // and jsx-runtime landed in the motion chunk; every chunk needs React,
        // so the "lazy" motion chunk was modulepreloaded by the entry on every
        // page, lesson and teacher screens included (2026-09-30 audit, F1).
        // Priorities make the claim explicit: React first.
        codeSplitting: {
          groups: [
            {
              name: 'vendor',
              test: /node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler)[\\/]/,
              priority: 30,
            },
            // Loaded eagerly by AuthContext.
            { name: 'supabase', test: /node_modules[\\/]@supabase[\\/]supabase-js[\\/]/, priority: 20 },
            // The `motion` runtime (motion / motion-dom / motion-utils) is used
            // only by lazy routes and a few shared components (CourseCard,
            // DashboardPage, the landing); the eager shell has none. Left to the
            // default heuristic it gets hoisted into the entry chunk. Pinned to
            // its own chunk, it loads only when a motion-using route mounts.
            { name: 'motion', test: /node_modules[\\/]motion(-dom|-utils)?[\\/]/, priority: 10 },
          ],
        },
      },
    },
  },
  server: {
    port: 3000,
    proxy: {
      // RUM batches go through our own origin in production (vercel.json,
      // `intakeProxyUrl` in src/lib/datadog.ts); the same path here, so a
      // dev build with Datadog configured behaves like the real one.
      '/_e': {
        target: 'https://browser-intake-us5-datadoghq.com',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/_e/, ''),
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Same-origin proxy for Supabase Storage public objects. Mirrors the
      // Vercel rewrites in frontend/vercel.json so local dev matches prod —
      // including which buckets are on the list. A wildcard here would let a
      // path work locally that production refuses, which is the worst way to
      // find out a bucket is private.
      '/img/course-assets': {
        target: process.env.VITE_SUPABASE_URL || 'https://rrisqutxlkamwfhcashl.supabase.co',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/img/, '/storage/v1/object/public'),
      },
      '/img/avatars': {
        target: process.env.VITE_SUPABASE_URL || 'https://rrisqutxlkamwfhcashl.supabase.co',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/img/, '/storage/v1/object/public'),
      },
    },
  },
})

