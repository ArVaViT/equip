import type { RumEvent } from "@datadog/browser-rum"

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
 *   3. **Google Fonts pulled in by a browser extension** — we self-host
 *      every typeface through ``@fontsource`` and reference
 *      ``fonts.gstatic.com`` nowhere, so a ``font-src`` block naming it
 *      cannot come from our own markup. In practice it's an extension
 *      rewriting the page's fonts in the visitor's browser: one such
 *      visitor produced 32 of these events in a single page load, and
 *      one of the blocked families (Instrument Serif) isn't even a
 *      dependency of this project. CSP is doing precisely its job by
 *      refusing the request — surfacing it as an application error is
 *      the only unhelpful part.
 *
 * Real CSP violations from our own assets still come through.
 */

/**
 * Hosts our own markup never requests, whose violations are therefore
 * always injected from outside the app.
 *
 * Deliberately an explicit list rather than a blanket "any third-party
 * origin" rule: a script pulled from an unexpected host is exactly the
 * signal this panel exists to surface, and a catch-all would bury it.
 */
const EXTENSION_INJECTED_HOSTS = [
  "fonts.gstatic.com",
  "fonts.googleapis.com",
  // Chrome's built-in page translator («Translate this page») loads its
  // bar from these. Our markup never requests them; a reader who asked
  // the browser to translate the page is not an application error.
  "translate.google.com",
  "translate.googleapis.com",
  "www.gstatic.com/_/translate_http",
]
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
  // Google Fonts injected by a browser extension — the blocked URI is
  // carried in the message, so match there rather than on the stack.
  if (EXTENSION_INJECTED_HOSTS.some((host) => message.includes(host))) return true
  return false
}

/**
 * three.js reporting that the browser has no WebGL to give it.
 *
 * The landing page's backdrop asks for a context on a throwaway canvas
 * first and renders nothing when there is none (`LandingBackdrop`), so the
 * page works — but three still writes the refusal to `console.error`, and
 * RUM records every console error as an application error. A machine
 * without a GPU (or with hardware acceleration switched off) is not a bug
 * in this app.
 */
export function isBenignWebGlRefusal(event: RumEvent): boolean {
  if (event.type !== "error") return false
  const message = (event as RumEvent & { error?: { message?: string } }).error?.message ?? ""
  return message.includes("THREE.WebGLRenderer") && message.includes("WebGL context could not be created")
}

/**
 * Browsers driven by a program, and crawlers — never recorded.
 *
 * Measured 2026-09-28 over the 30 days RUM keeps: 825 sessions, of which
 * roughly 360 were the CI job «Production language check» (Playwright on
 * GitHub's Azure runners, sweeping pl/uk/ru locales at 1280×720, ~10 a
 * day), about 100 were local Playwright runs against production, and ~25
 * were search and link-preview crawlers. Every one counted as a user
 * session, sat in the session list next to real students, and fed the LCP
 * and error monitors numbers that were not anybody's experience.
 *
 * `navigator.webdriver` is the standard flag every automation driver sets
 * (Playwright, Puppeteer, Selenium), headless or not. The user-agent test
 * catches crawlers, which do not set it. The pattern needs a `/` after the
 * word — every crawler names a version (`Googlebot/2.1`, `ShapBot/0.1`) —
 * so a phone called «CUBOT X30» is not mistaken for one.
 */
const CRAWLER_UA = /[a-z-]*(?:bot|crawler|spider|webindexer)\/|headlesschrome|lighthouse/i

export function isAutomatedVisitor(nav: Pick<Navigator, "userAgent"> & { webdriver?: boolean }): boolean {
  return nav.webdriver === true || CRAWLER_UA.test(nav.userAgent)
}

/**
 * Where the SDK sends its batches: through our own domain.
 *
 * Content blockers (uBlock Origin's default lists, Brave, Firefox strict
 * mode) block `browser-intake-*-datadoghq.com` outright, so for those
 * visitors RUM loads, records, and never delivers — no session, no replay,
 * no error. On 2026-09-28 a user who signed up with Google at 22:33 UTC on
 * 22.09 left no session at all in that hour.
 *
 * `vercel.json` rewrites `/_e/*` to the us5 intake; the path is neutral on
 * purpose, because blockers also match words like `rum` and `datadog` in
 * first-party paths. The query string (client token, source, batch id)
 * rides along unchanged.
 */
export function intakeProxyUrl({ path, parameters }: { path: string; parameters: string }): string {
  return `${window.location.origin}/_e${path}?${parameters}`
}

/**
 * Credentials a URL can carry on this site, and the text RUM copies URLs into.
 *
 * Found in RUM on 2026-09-16: `view.url` held
 * `/invite/accept?token=<invitation token>` for every invited visitor, and
 * `/auth/callback#access_token=…&provider_token=…&refresh_token=…` for
 * every Google sign-in — a live session, and the Google token behind it,
 * indexed for as long as RUM keeps a view. RUM copies the page URL into
 * `view.url`, the previous page into `view.referrer`, every request into
 * `resource.url`, and any URL an error mentions into its message and stack.
 *
 * What counts as a secret mirrors the backend's `app/core/redact.py`:
 *
 * - the path segment after `/invitations/token/` (the preview route a
 *   stale bundle may still call);
 * - query or fragment parameters that carry a credential — `token`,
 *   `access_token`, `refresh_token`, `provider_token`,
 *   `provider_refresh_token`, `id_token`, `token_hash`, `code`;
 * - any JWT, wherever it appears.
 *
 * Not secret, and left readable: `error`, `error_code`, `token_type`,
 * `expires_in`, resource ids, certificate numbers (printed on the
 * certificate so a stranger can check them).
 */
const REDACTED = "[redacted]"
const SECRET_PATH = /(\/invitations\/token\/)[^/?#\s'"]+/g
const SECRET_PARAMS = [
  "token",
  "access_token",
  "refresh_token",
  "provider_token",
  "provider_refresh_token",
  "id_token",
  "token_hash",
  "code",
]
const SECRET_PARAM = new RegExp(`([?&#])(${SECRET_PARAMS.join("|")})=[^&#\\s'"]+`, "g")
const JWT = /eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g

export function redactSecrets(text: string): string
export function redactSecrets(text: string | undefined): string | undefined
export function redactSecrets(text: string | undefined): string | undefined {
  if (!text) return text
  return text
    .replace(SECRET_PATH, `$1${REDACTED}`)
    .replace(SECRET_PARAM, `$1$2=${REDACTED}`)
    .replace(JWT, REDACTED)
}

type Scrubbable = {
  view?: { url?: string; referrer?: string }
  resource?: { url?: string }
  error?: { message?: string; stack?: string; resource?: { url?: string } }
}

/**
 * Remove credentials from every field of a RUM event that holds a URL.
 *
 * Mutates in place: `beforeSend` is handed the event to edit, and these
 * are fields Datadog documents as modifiable there. Every event type
 * carries `view`, so the page URL is cleaned on views, actions, resources,
 * errors and long tasks alike.
 */
export function scrubRumEvent(event: RumEvent): void {
  const e = event as RumEvent & Scrubbable
  if (e.view) {
    e.view.url = redactSecrets(e.view.url)
    e.view.referrer = redactSecrets(e.view.referrer)
  }
  if (e.resource) e.resource.url = redactSecrets(e.resource.url)
  if (e.error) {
    e.error.message = redactSecrets(e.error.message)
    e.error.stack = redactSecrets(e.error.stack)
    if (e.error.resource) e.error.resource.url = redactSecrets(e.error.resource.url)
  }
}

/** The `beforeSend` hook: drop benign noise, scrub everything else. */
export function beforeSendRum(event: RumEvent): boolean {
  if (isBenignCspViolation(event)) return false
  if (isBenignWebGlRefusal(event)) return false
  scrubRumEvent(event)
  return true
}

/**
 * The SDK, once it is loaded and started; null when RUM is off for this load.
 *
 * Loaded with a dynamic import, not a static one, since 2026-10-15. The SDK
 * is ~45 kB gzipped — about 40% of what the entry chunk weighed — and as a
 * static import it sat in front of the first paint on every page, for every
 * visitor, including the automated ones it then declines to start for. On a
 * phone that was a direct share of the landing page's LCP.
 *
 * The cost is the window before the chunk arrives. Datadog's own async
 * (CDN) setup has the same window, and covers it the same way: the view's
 * timings come from buffered performance entries, so the first view's FCP
 * and LCP are still recorded; route changes are queued by the React plugin
 * (`onRumInit`) and replayed at init; and errors thrown before init are kept
 * by `bufferEarlyErrors` below and handed over once it runs.
 *
 * Whether RUM is configured (the `VITE_DATADOG_*` ids) is decided inside the
 * lazy chunk, not here. Checked here, the bundler folds the check away on a
 * build without the ids — CI, a local build — and drops the chunk with it,
 * so the bundle-size sentinel would see different chunks in CI than on
 * Vercel. Without the ids the chunk is fetched and starts nothing; that
 * happens only off production.
 */
type DatadogRum = typeof import("@datadog/browser-rum")["datadogRum"]
let rumReady: Promise<DatadogRum | null> | null = null

/**
 * Uncaught errors from before the SDK is up. Bounded — a boot that throws in
 * a loop must not grow this without limit — and dropped the moment RUM takes
 * over, which installs its own listeners.
 */
const EARLY_ERROR_LIMIT = 20
function bufferEarlyErrors(): () => unknown[] {
  const early: unknown[] = []
  const onError = (event: ErrorEvent) => {
    if (early.length < EARLY_ERROR_LIMIT) early.push(event.error ?? event.message)
  }
  const onRejection = (event: PromiseRejectionEvent) => {
    if (early.length < EARLY_ERROR_LIMIT) early.push(event.reason)
  }
  window.addEventListener("error", onError)
  window.addEventListener("unhandledrejection", onRejection)
  return () => {
    window.removeEventListener("error", onError)
    window.removeEventListener("unhandledrejection", onRejection)
    return early
  }
}

export function initDatadogRum() {
  // Not started at all, rather than started and filtered: an automated
  // run should cost nothing and leave nothing (see `isAutomatedVisitor`).
  // Since the SDK became a lazy chunk, "nothing" includes the download.
  if (isAutomatedVisitor(navigator)) return

  const takeEarlyErrors = bufferEarlyErrors()
  rumReady = import("./datadogRum")
    .then(({ startRum }) => {
      const rum = startRum()
      const early = takeEarlyErrors()
      if (rum) for (const error of early) rum.addError(error, { early: true })
      return rum
    })
    .catch(() => {
      // A blocked or failed chunk: no monitoring for this load, and no
      // reason to take the page down over it.
      takeEarlyErrors()
      return null
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
  void rumReady?.then((rum) =>
    rum?.setUser({
      id: user.id,
      ...(user.email ? { email: user.email } : {}),
      ...(user.name ? { name: user.name } : {}),
      ...(user.role ? { role: user.role } : {}),
    }),
  )
}

export function clearDatadogUser() {
  void rumReady?.then((rum) => rum?.clearUser())
}

/**
 * Report an error RUM would not see by itself (one React caught). Waits for
 * the SDK when it is still loading; a no-op when RUM is off for this load.
 */
export function reportDatadogError(error: unknown, context?: object) {
  void rumReady?.then((rum) => rum?.addError(error, context))
}
