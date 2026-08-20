import axios, { isAxiosError } from "axios"
import type { AxiosRequestConfig, AxiosResponse, InternalAxiosRequestConfig } from "axios"
import i18n, { DEFAULT_LOCALE, isSupportedLocale } from "@/i18n/config"
import { supabase } from "@/lib/supabase"

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"
const cleanApiUrl = API_URL.replace(/\/+$/, "")

const api = axios.create({
  baseURL: `${cleanApiUrl}/api/v1`,
  headers: { "Content-Type": "application/json" },
})

type RetriableConfig = InternalAxiosRequestConfig & { _retry?: boolean }

let cachedToken: string | null = null

// Prime the cache on module load, and keep it in sync with Supabase auth events.
// Before the first `getSession()` resolves we fall back to a live lookup inside
// the request interceptor so early calls still ship an Authorization header.
let primed: Promise<void> | null = supabase.auth
  .getSession()
  .then(({ data }) => {
    cachedToken = data.session?.access_token ?? null
  })
  .catch(() => {
    cachedToken = null
  })
  .finally(() => {
    primed = null
  })

supabase.auth.onAuthStateChange((_event, session) => {
  cachedToken = session?.access_token ?? null
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

async function getAccessToken(): Promise<string | null> {
  if (cachedToken) return cachedToken
  if (primed) {
    try {
      await primed
    } catch {
      // `primed` itself swallows errors; leave cachedToken null.
    }
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
        cachedToken = null
        await supabase.auth.signOut()
        return null
      }
      cachedToken = newToken
      return newToken
    } catch {
      cachedToken = null
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
