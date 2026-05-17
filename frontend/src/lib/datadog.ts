import { datadogRum, type RumEvent } from "@datadog/browser-rum"
import { reactPlugin } from "@datadog/browser-rum-react"

/**
 * CSP-Report-Only violations RUM forwards to Datadog as ``@type:error``
 * events. Most are real config drift we want to see; a few signatures
 * are *structurally* benign and just inflate the error-rate panel:
 *
 *   1. **Zod 4 feature-detect** — at module load Zod runs
 *      ``try { Function(""); return true } catch { return false }`` to
 *      probe whether the runtime supports ``new Function()`` for schema
 *      compilation. The probe is wrapped in try/catch so it never
 *      breaks; CSP ``script-src 'self'`` (no ``'unsafe-eval'``) reports
 *      it anyway. We'd rather keep CSP strict than whitelist eval to
 *      silence the probe — the trade-off is a known-benign error
 *      signature, which we filter here.
 *
 *   2. **Vercel preview-comments overlay** (``vercel.live``) — Vercel
 *      injects the feedback toolbar on deployments **for the project
 *      owner** (not anonymous users). The toolbar loads ``geist.woff2``
 *      and ``geist_mono.woff2`` from ``vercel.live`` and trips
 *      ``font-src`` / ``script-src``. Real visitors don't see this;
 *      it's noise from owner browsing. Filtering it keeps the panel
 *      honest without adding ``vercel.live`` to every CSP directive.
 *
 * Real CSP violations from our own assets still come through.
 */
export function isBenignCspViolation(event: RumEvent): boolean {
  if (event.type !== "error") return false
  const err = (event as RumEvent & { error?: { message?: string; stack?: string } }).error
  if (!err) return false
  const message = err.message ?? ""
  const stack = err.stack ?? ""
  if (!message.includes("csp_violation")) return false
  // Zod schemas chunk feature-detect — try/catch protected, no behavior change.
  if (stack.includes("/assets/schemas-")) return true
  // Vercel preview-comments overlay — only loads for the project owner.
  if (stack.includes("vercel.live") || message.includes("vercel.live")) return true
  return false
}

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

    // Drop known-benign CSP-Report-Only violation events client-side
    // (see ``isBenignCspViolation`` for the signatures + rationale).
    // Returning ``false`` here prevents the event from being sent to
    // Datadog; everything else passes through unchanged.
    beforeSend: (event) => !isBenignCspViolation(event),
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
