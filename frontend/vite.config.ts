import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// VERCEL_GIT_COMMIT_SHA is injected by Vercel at build time. Falls back to
// 'dev' for local builds so Datadog RUM can still tag events with a version.
const appVersion =
  process.env.VITE_APP_VERSION ||
  (process.env.VERCEL_GIT_COMMIT_SHA ? process.env.VERCEL_GIT_COMMIT_SHA.slice(0, 7) : 'dev')

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
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

