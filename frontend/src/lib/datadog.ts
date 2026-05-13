import { datadogRum } from "@datadog/browser-rum"
import { reactPlugin } from "@datadog/browser-rum-react"

// Datadog RUM is opt-in: if the applicationId / clientToken aren't set we
// skip init entirely so local builds don't ship events to a dashboard nobody
// reads. In production (Vercel) both vars are populated from Vercel env vars.

/**
 * Extract the backend origin from VITE_API_URL so we can mark fetch/XHR
 * calls to our own API as "first-party" — this is what links RUM sessions
 * to backend APM traces once we turn APM on. If the URL is malformed or
 * unset we fall back to an empty array (no tracing headers added).
 */
function buildAllowedTracingUrls(): (string | RegExp)[] {
  const apiUrl = import.meta.env.VITE_API_URL
  if (!apiUrl) return []
  try {
    const origin = new URL(apiUrl).origin
    return [origin]
  } catch {
    return []
  }
}

export function initDatadogRum() {
  const applicationId = import.meta.env.VITE_DATADOG_APPLICATION_ID
  const clientToken = import.meta.env.VITE_DATADOG_CLIENT_TOKEN
  if (!applicationId || !clientToken) return

  const env = import.meta.env.VITE_DATADOG_ENV ?? import.meta.env.MODE
  const site = import.meta.env.VITE_DATADOG_SITE ?? "us5.datadoghq.com"
  const service = import.meta.env.VITE_DATADOG_SERVICE ?? "equip-frontend"
  const version = import.meta.env.VITE_APP_VERSION ?? "0.0.0"

  datadogRum.init({
    applicationId,
    clientToken,
    site,
    service,
    env,
    version,

    // 100% of sessions — at our scale (tens of users) sampling just wastes
    // visibility. Bump down later if volume ever grows.
    sessionSampleRate: 100,
    // Session Replay also at 100%. Per-replay cost is ~$0.006 on US5 and our
    // volume is tiny; we'd rather always have the video when debugging a bug
    // report than have to ask the user to reproduce.
    sessionReplaySampleRate: 100,

    // Privacy: mask every text input by default — quiz answers, student
    // names, password fields, chat-style pages all contain PII that must
    // not end up in replay recordings. Non-input text (buttons, headings,
    // course content) is still visible.
    defaultPrivacyLevel: "mask-user-input",

    // Full auto-instrumentation: page loads, resource timings (XHR/fetch/
    // images/CSS/JS), click/scroll/input actions, long tasks (>50ms JS
    // blocking the main thread), frustration signals (rage clicks, dead
    // clicks, error clicks).
    trackResources: true,
    trackUserInteractions: true,
    trackLongTasks: true,

    // Connects RUM sessions to backend APM traces. When the backend adds
    // the Datadog tracer, requests to our API will carry the trace headers
    // and a "View API Calls" tab will show end-to-end waterfalls.
    allowedTracingUrls: buildAllowedTracingUrls(),
    traceSampleRate: 100,

    // React Router v6 integration — uses the drop-in <Routes> from
    // @datadog/browser-rum-react/react-router-v6 to create one RUM view
    // per route *template* (e.g. "/courses/:id") instead of per-URL so
    // "/courses/abc-uuid" and "/courses/def-uuid" aggregate into the
    // same view in dashboards.
    plugins: [reactPlugin({ router: true })],
  })
}

/**
 * Identify the logged-in user on the current RUM session. Called from
 * AuthContext whenever we have a profile loaded. ID + email + name land on
 * every subsequent session/view/error/action until ``clearDatadogUser`` is
 * called, so you can filter by user or see "who saw this bug" in Session
 * Replay.
 */
export function setDatadogUser(user: {
  id: string
  email?: string | null
  name?: string | null
  role?: string | null
}) {
  if (!import.meta.env.VITE_DATADOG_APPLICATION_ID) return
  datadogRum.setUser({
    id: user.id,
    ...(user.email ? { email: user.email } : {}),
    ...(user.name ? { name: user.name } : {}),
    ...(user.role ? { role: user.role } : {}),
  })
}

export function clearDatadogUser() {
  if (!import.meta.env.VITE_DATADOG_APPLICATION_ID) return
  datadogRum.clearUser()
}
