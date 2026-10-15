import { datadogRum } from "@datadog/browser-rum"
import { reactPlugin } from "@datadog/browser-rum-react"
import { beforeSendRum, intakeProxyUrl } from "./datadog"

/**
 * The Datadog RUM SDK and its configuration — a lazy chunk, loaded by
 * `initDatadogRum` in `./datadog.ts` (which explains why it is lazy). The
 * event filters it installs live there too, so they stay testable without
 * the SDK.
 */

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

export function startRum(): typeof datadogRum | null {
  const applicationId = import.meta.env.VITE_DATADOG_APPLICATION_ID
  const clientToken = import.meta.env.VITE_DATADOG_CLIENT_TOKEN
  // Datadog RUM is opt-in: if the applicationId / clientToken aren't set we
  // skip init entirely so local builds don't ship events to a dashboard nobody
  // reads. In production (Vercel) both vars are populated from Vercel env vars.
  if (!applicationId || !clientToken) return null

  const env = import.meta.env.VITE_DATADOG_ENV ?? import.meta.env.MODE
  const site = import.meta.env.VITE_DATADOG_SITE ?? "us5.datadoghq.com"
  const service = import.meta.env.VITE_DATADOG_SERVICE ?? "equip-frontend"
  const version = import.meta.env.VITE_APP_VERSION ?? "0.0.0"

  datadogRum.init({
    applicationId,
    clientToken,
    site,
    proxy: intakeProxyUrl,
    service,
    env,
    version,

    // 100% of sessions — at our scale (tens of users) sampling just wastes
    // visibility, and the LCP/error monitors need full coverage. RUM session
    // events are cheap; keep them all.
    sessionSampleRate: 100,
    // Session Replay at 100% for the pilot. The recorder serializes DOM
    // mutations from first paint and can compete for the main thread during
    // the LCP window (that's why it was cut to 20% during the perf audit),
    // but with real pilot users now onboarding, seeing every session is worth
    // far more than the LCP artifact or the (negligible-at-this-scale) replay
    // cost. Revisit if session volume grows enough that replay cost or the
    // main-thread overhead actually bites.
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
    // (see ``isBenignCspViolation`` for the signatures + rationale), and
    // strip credentials out of the URLs on everything else (see
    // ``scrubRumEvent``). Returning ``false`` prevents the event from
    // being sent to Datadog.
    beforeSend: beforeSendRum,
  })
  return datadogRum
}
