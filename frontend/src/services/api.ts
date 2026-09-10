import axios, { isAxiosError } from "axios"
import type { AxiosRequestConfig, AxiosResponse, InternalAxiosRequestConfig } from "axios"
import i18n, { DEFAULT_LOCALE, isSupportedLocale } from "@/i18n/config"
import { supabase } from "@/lib/supabase"
import { rememberSignOutReason } from "@/lib/signOutReason"

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"
const cleanApiUrl = API_URL.replace(/\/+$/, "")

const api = axios.create({
  baseURL: `${cleanApiUrl}/api/v1`,
  headers: { "Content-Type": "application/json" },
})

type RetriableConfig = InternalAxiosRequestConfig & { _retry?: boolean }

let cachedToken: string | null = null
/** Unix seconds, straight off the session. `null` when unknown. */
let cachedExpiresAt: number | null = null

// How stale a cached token may be before we go back to Supabase for it.
// Below `EXPIRY_MARGIN_MS` (90s in auth-js), `getSession()` refreshes rather
// than hands back what it has, so anything under that number means "ask and
// you will get a new one".
const REFRESH_BEFORE_EXPIRY_S = 60

function rememberSession(session: { access_token: string; expires_at?: number } | null) {
  cachedToken = session?.access_token ?? null
  cachedExpiresAt = session?.expires_at ?? null
}

// Prime the cache on module load, and keep it in sync with Supabase auth events.
// Before the first `getSession()` resolves we fall back to a live lookup inside
// the request interceptor so early calls still ship an Authorization header.
let primed: Promise<void> | null = supabase.auth
  .getSession()
  .then(({ data }) => {
    rememberSession(data.session ?? null)
  })
  .catch(() => {
    rememberSession(null)
  })
  .finally(() => {
    primed = null
  })

supabase.auth.onAuthStateChange((_event, session) => {
  rememberSession(session ?? null)
})

function currentAcceptLanguage(): string {
  // The three rungs all end at DEFAULT_LOCALE rather than a literal: this
  // header is what the server resolves content in, so a value here that
  // disagreed with the constant would have the API answering in one
  // language while the interface around it rendered in another.
  const raw = (i18n.resolvedLanguage ?? i18n.language ?? DEFAULT_LOCALE).toLowerCase()
  const head = raw.split("-", 1)[0] ?? DEFAULT_LOCALE
  return isSupportedLocale(head) ? head : DEFAULT_LOCALE
}

/**
 * True while the cached token has more than `REFRESH_BEFORE_EXPIRY_S` of
 * life left. An unknown expiry counts as fresh: the 401 path below is the
 * backstop, and refusing to send a token we cannot date would log people
 * out over a missing field.
 */
function cachedTokenIsFresh(): boolean {
  if (cachedExpiresAt === null) return true
  return cachedExpiresAt - REFRESH_BEFORE_EXPIRY_S > Date.now() / 1000
}

// One `getSession()` at a time. A page that fires six calls on mount would
// otherwise ask six times over.
let sessionLookup: Promise<void> | null = null

function syncSessionOnce(): Promise<void> {
  sessionLookup ??= supabase.auth
    .getSession()
    .then(({ data }) => {
      // `getSession()` refreshes an access token inside its expiry margin
      // and hands back the new one, so a session that survived is already
      // updated here. A session that did not survive comes back null, and
      // the request goes out unauthenticated — same as before a login.
      rememberSession(data.session ?? null)
    })
    .catch(() => {
      // Network trouble mid-refresh. Keep the token we have: it may still
      // be good, and if it is not, the 401 path answers properly. Wiping
      // the cache here would turn a dropped packet into a sign-out.
    })
    .finally(() => {
      sessionLookup = null
    })
  return sessionLookup
}

/**
 * The token to send, refreshed first when it is about to expire.
 *
 * Without the freshness check this returned whatever the last auth event
 * cached, expiry be damned. auth-js only auto-refreshes while the tab is
 * visible and awake, so a lesson editor left open overnight kept sending an
 * hour-old JWT: production logged a 401 on `/translation-progress` and
 * `/notifications/unread-count` every 61 minutes on 2026-09-07 and -08 for
 * the one teacher using the product. The 401 interceptor did recover each
 * one, but the round trip is wasted, and any GET whose caller does not
 * retry — the polling ones above — just shows nothing.
 */
async function getAccessToken(): Promise<string | null> {
  if (primed) {
    try {
      await primed
    } catch {
      // `primed` itself swallows errors; leave the cache as it is.
    }
  }
  if (cachedToken && !cachedTokenIsFresh()) {
    await syncSessionOnce()
  }
  return cachedToken
}

api.interceptors.request.use(async (config) => {
  config.headers["Accept-Language"] = currentAcceptLanguage()
  const token = await getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Coalesce concurrent 401s into a single refreshSession() call. Without this,
// N in-flight requests each call refreshSession() and signOut() in parallel —
// multiple refresh tokens burn, and the last signOut wins, bouncing the user
// even if an earlier refresh actually succeeded.
let refreshInflight: Promise<string | null> | null = null

function refreshAccessTokenOnce(): Promise<string | null> {
  if (refreshInflight) return refreshInflight
  refreshInflight = (async () => {
    try {
      const { data, error: refreshError } = await supabase.auth.refreshSession()
      const newToken = data.session?.access_token ?? null
      if (refreshError || !newToken) {
        rememberSession(null)
        // Said before the sign-out, because the sign-out is what swaps the
        // page for the login form — and the form is where this is read.
        rememberSignOutReason("session_expired")
        await supabase.auth.signOut()
        return null
      }
      rememberSession(data.session ?? null)
      return newToken
    } catch {
      rememberSession(null)
      rememberSignOutReason("session_expired")
      await supabase.auth.signOut()
      return null
    } finally {
      refreshInflight = null
    }
  })()
  return refreshInflight
}

api.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    // A soft-deleted account returns 403 ``account.deactivated`` on every
    // authenticated call. Eject the user cleanly to the auth screens instead
    // of leaving them on a wall of generic permission errors.
    if (isAxiosError(error) && error.response?.status === 403) {
      const code = (error.response.data as { detail?: { code?: string } } | undefined)?.detail?.code
      if (code === "account.deactivated") {
        rememberSignOutReason("account_deactivated")
        await supabase.auth.signOut()
        return Promise.reject(error)
      }
    }
    if (!isAxiosError(error) || error.response?.status !== 401) {
      return Promise.reject(error)
    }

    const original = error.config as RetriableConfig | undefined
    if (!original || original._retry) {
      return Promise.reject(error)
    }
    original._retry = true

    // Try to transparently recover from a stale/expired access token before
    // ejecting the user. A truly invalid session — refresh fails or the retry
    // still returns 401 — falls through to signOut so the UI re-renders to the
    // auth screens instead of looping.
    const newToken = await refreshAccessTokenOnce()
    if (!newToken) {
      return Promise.reject(error)
    }
    original.headers = original.headers ?? {}
    original.headers.Authorization = `Bearer ${newToken}`
    return api.request(original)
  },
)

const inflight = new Map<string, Promise<AxiosResponse<unknown>>>()

function dedupeKey(url: string, token: string | null, params?: Record<string, unknown>): string {
  // Include the auth token in the key so a request that fires right before
  // login doesn't get its unauthenticated response served to a logged-in
  // caller a millisecond later. Include Accept-Language so a locale change
  // does not serve a cached payload from a previous `i18n` language.
  const tokenBucket = token ? token.slice(-12) : "anon"
  const lang = currentAcceptLanguage()
  return params
    ? `${url}?${JSON.stringify(params)}|${tokenBucket}|${lang}`
    : `${url}|${tokenBucket}|${lang}`
}

const originalGet = api.get.bind(api)

api.get = function dedupedGet<T = unknown, R = AxiosResponse<T>, D = unknown>(
  url: string,
  config?: AxiosRequestConfig<D>,
): Promise<R> {
  const key = dedupeKey(url, cachedToken, config?.params as Record<string, unknown> | undefined)
  const existing = inflight.get(key)
  if (existing) return existing as Promise<R>

  // axios 1.19 stopped returning `Promise<R>` from its instance methods and
  // switched to `Promise<AxiosResponseResult<T, R, D, P>>` — a conditional
  // that resolves to `AxiosResponse<T, D, {}, P>` when the caller left `R` at
  // axios' internal `AxiosResponseDefault` sentinel, and to `R` otherwise.
  // That distinction is exactly what this wrapper cannot express: it declares
  // its own `R = AxiosResponse<T>` default, so from the compiler's side `R`
  // is an open type parameter that might be the sentinel, and the conditional
  // stays unresolved. `AxiosResponseResult` isn't exported, so we can't mirror
  // the signature either. The assignment below is already reconciled with
  // `as typeof api.get`; this cast is the same reconciliation one level down.
  // Purely type-level — dedupe behaviour is unchanged.
  const promise = (originalGet<T, R, D>(url, config) as Promise<R>).finally(() => {
    inflight.delete(key)
  })
  inflight.set(key, promise as Promise<AxiosResponse<unknown>>)
  return promise
} as typeof api.get

export default api
