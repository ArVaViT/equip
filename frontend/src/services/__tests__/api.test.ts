import axios from "axios"
import MockAdapter from "axios-mock-adapter"
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest"
import { takeSignOutReason } from "@/lib/signOutReason"

// We need to mock supabase BEFORE importing api.ts, because api.ts primes
// the token cache at module load and also attaches an onAuthStateChange
// listener. The supabase mock must expose getSession / refreshSession /
// signOut / onAuthStateChange so those calls don't explode under jsdom.

const getSession = vi.fn()
const refreshSession = vi.fn()
const signOut = vi.fn()
const onAuthStateChange = vi.fn().mockReturnValue({
  data: { subscription: { unsubscribe: vi.fn() } },
})

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      getSession,
      refreshSession,
      signOut,
      onAuthStateChange,
    },
  },
}))

async function freshApi() {
  // Re-import api.ts so interceptors and token cache reset for each test.
  vi.resetModules()
  const mod = await import("../api")
  return mod.default
}

describe("api interceptors", () => {
  beforeEach(() => {
    getSession.mockReset()
    refreshSession.mockReset()
    signOut.mockReset()
    onAuthStateChange.mockClear()
    window.sessionStorage.clear()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it("attaches the cached access token as a Bearer header", async () => {
    getSession.mockResolvedValue({
      data: { session: { access_token: "test-token-123" } },
    })
    const api = await freshApi()
    const mock = new MockAdapter(api)
    mock.onGet("/ping").reply((config) => {
      expect(config.headers?.Authorization).toBe("Bearer test-token-123")
      return [200, { ok: true }]
    })

    const res = await api.get("/ping")
    expect(res.data).toEqual({ ok: true })
  })

  it("omits Authorization when no session exists", async () => {
    getSession.mockResolvedValue({ data: { session: null } })
    const api = await freshApi()
    const mock = new MockAdapter(api)
    mock.onGet("/public").reply((config) => {
      expect(config.headers?.Authorization).toBeUndefined()
      return [200, {}]
    })

    await api.get("/public")
  })

  it("transparently retries a 401 after refreshing the session", async () => {
    getSession.mockResolvedValue({
      data: { session: { access_token: "old" } },
    })
    refreshSession.mockResolvedValue({
      data: { session: { access_token: "new" } },
      error: null,
    })

    const api = await freshApi()
    const mock = new MockAdapter(api)
    let attempt = 0
    mock.onGet("/me").reply((config) => {
      attempt += 1
      if (attempt === 1) {
        expect(config.headers?.Authorization).toBe("Bearer old")
        return [401]
      }
      expect(config.headers?.Authorization).toBe("Bearer new")
      return [200, { id: "u1" }]
    })

    const res = await api.get("/me")
    expect(attempt).toBe(2)
    expect(res.data).toEqual({ id: "u1" })
    expect(signOut).not.toHaveBeenCalled()
  })

  it("signs the user out when refresh fails on a 401", async () => {
    getSession.mockResolvedValue({
      data: { session: { access_token: "old" } },
    })
    refreshSession.mockResolvedValue({
      data: { session: null },
      error: { message: "refresh failed" },
    })
    signOut.mockResolvedValue({ error: null })

    const api = await freshApi()
    const mock = new MockAdapter(api)
    mock.onGet("/me").reply(401)

    await expect(api.get("/me")).rejects.toHaveProperty(
      "response.status",
      401,
    )
    expect(signOut).toHaveBeenCalledTimes(1)
    // The login form the sign-out lands on reads this and says «session
    // expired» — instead of appearing out of nowhere, mid-sentence.
    expect(takeSignOutReason()).toBe("session_expired")
  })

  it("leaves the reason behind when the server says the account is deactivated", async () => {
    getSession.mockResolvedValue({
      data: { session: { access_token: "tok" } },
    })
    signOut.mockResolvedValue({ error: null })

    const api = await freshApi()
    const mock = new MockAdapter(api)
    mock.onGet("/me").reply(403, { detail: { code: "account.deactivated", message: "Deactivated" } })

    await expect(api.get("/me")).rejects.toHaveProperty("response.status", 403)
    expect(signOut).toHaveBeenCalledTimes(1)
    expect(takeSignOutReason()).toBe("account_deactivated")
  })

  it("does not retry a single request more than once on 401", async () => {
    getSession.mockResolvedValue({
      data: { session: { access_token: "old" } },
    })
    refreshSession.mockResolvedValue({
      data: { session: { access_token: "new" } },
      error: null,
    })
    signOut.mockResolvedValue({ error: null })

    const api = await freshApi()
    const mock = new MockAdapter(api)
    let calls = 0
    mock.onGet("/me").reply(() => {
      calls += 1
      return [401]
    })

    await expect(api.get("/me")).rejects.toHaveProperty(
      "response.status",
      401,
    )
    // First call + one retry = 2 requests before giving up.
    expect(calls).toBe(2)
  })

  it("lets non-401 errors bubble up unchanged", async () => {
    getSession.mockResolvedValue({ data: { session: null } })
    const api = await freshApi()
    const mock = new MockAdapter(api)
    mock.onGet("/boom").reply(500, { detail: "kaboom" })

    await expect(api.get("/boom")).rejects.toSatisfy((err: unknown) => {
      return axios.isAxiosError(err) && err.response?.status === 500
    })
    expect(refreshSession).not.toHaveBeenCalled()
    expect(signOut).not.toHaveBeenCalled()
  })

  it("dedupes concurrent GETs to the same URL+auth bucket", async () => {
    getSession.mockResolvedValue({
      data: { session: { access_token: "tok" } },
    })
    const api = await freshApi()
    const mock = new MockAdapter(api, { delayResponse: 30 })
    let hits = 0
    mock.onGet("/list").reply(() => {
      hits += 1
      return [200, [1, 2, 3]]
    })

    const [a, b, c] = await Promise.all([
      api.get("/list"),
      api.get("/list"),
      api.get("/list"),
    ])
    expect(hits).toBe(1)
    expect(a.data).toEqual([1, 2, 3])
    expect(b.data).toEqual([1, 2, 3])
    expect(c.data).toEqual([1, 2, 3])
  })

  it("does not dedupe when query params differ", async () => {
    getSession.mockResolvedValue({
      data: { session: { access_token: "tok" } },
    })
    const api = await freshApi()
    const mock = new MockAdapter(api, { delayResponse: 15 })
    let hits = 0
    mock.onGet("/search").reply(() => {
      hits += 1
      return [200, []]
    })

    await Promise.all([
      api.get("/search", { params: { q: "a" } }),
      api.get("/search", { params: { q: "b" } }),
    ])
    expect(hits).toBe(2)
  })
})
