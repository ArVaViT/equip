import { act, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { Session, User as SupabaseUser } from "@supabase/supabase-js"

// Supabase and authService must be mocked BEFORE importing the provider,
// because the provider subscribes to onAuthStateChange on mount.

type AuthChangeHandler = (event: string, session: Session | null) => void

let authHandler: AuthChangeHandler | null = null
const unsubscribe = vi.fn()

const from = vi.fn()

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      onAuthStateChange: vi.fn((cb: AuthChangeHandler) => {
        authHandler = cb
        return { data: { subscription: { unsubscribe } } }
      }),
      // Resolve to "no session" — the AuthContext doesn't actually care
      // about this value (it relies on the onAuthStateChange callback),
      // but ``services/api.ts`` reads it at module load to prime its
      // bearer-token cache and crashes if it's not thenable.
      getSession: vi
        .fn()
        .mockResolvedValue({ data: { session: null }, error: null }),
    },
    from: (...args: unknown[]) => from(...args),
  },
}))

// New dependency of ``AuthContext`` for post-OAuth locale reconciliation.
// Tests in this file never exercise that path, so just stub the call.
vi.mock("@/services/preferences", () => ({
  preferencesService: {
    setPreferredLocale: vi.fn().mockResolvedValue({}),
  },
}))

const login = vi.fn()
const register = vi.fn()
const signInWithGoogle = vi.fn()
const resetPassword = vi.fn()
const logout = vi.fn()

vi.mock("@/services/auth", () => ({
  authService: {
    login: (...a: unknown[]) => login(...a),
    register: (...a: unknown[]) => register(...a),
    signInWithGoogle: (...a: unknown[]) => signInWithGoogle(...a),
    resetPassword: (...a: unknown[]) => resetPassword(...a),
    logout: (...a: unknown[]) => logout(...a),
  },
}))

import { AuthProvider } from "../AuthContext"
import { useAuth } from "../useAuth"

function AuthProbe() {
  const { user, loading, logout: doLogout } = useAuth()
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="user">{user ? user.email : "anon"}</span>
      <span data-testid="role">{user?.role ?? "-"}</span>
      <button onClick={() => doLogout()}>sign out</button>
    </div>
  )
}

function makeSupabaseUser(overrides: Partial<SupabaseUser> = {}): SupabaseUser {
  return {
    id: "user-1",
    email: "a@b.com",
    app_metadata: {},
    user_metadata: { role: "student", full_name: "A" },
    aud: "authenticated",
    created_at: "2024-01-01T00:00:00Z",
    ...overrides,
  } as SupabaseUser
}

function makeSession(user: SupabaseUser): Session {
  return {
    access_token: "tok",
    refresh_token: "r",
    expires_in: 3600,
    token_type: "bearer",
    user,
  } as unknown as Session
}

function mockProfileFetch(profile: Record<string, unknown> | null, error?: unknown) {
  // supabase.from(...).select(...).eq(...).single() returns a thenable that
  // yields `{ data, error }`.
  const single = vi.fn().mockResolvedValue({ data: profile, error: error ?? null })
  const eq = vi.fn().mockReturnValue({ single })
  const select = vi.fn().mockReturnValue({ eq })
  from.mockReturnValue({ select })
  return { single, eq, select }
}

describe("AuthContext", () => {
  beforeEach(() => {
    authHandler = null
    unsubscribe.mockReset()
    from.mockReset()
    login.mockReset()
    register.mockReset()
    signInWithGoogle.mockReset()
    resetPassword.mockReset()
    logout.mockReset()
  })

  it("starts in a loading=true, anon state until INITIAL_SESSION fires", () => {
    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    )
    expect(screen.getByTestId("loading").textContent).toBe("true")
    expect(screen.getByTestId("user").textContent).toBe("anon")
  })

  it("flips loading=false and populates the user on INITIAL_SESSION with a session", async () => {
    mockProfileFetch({
      id: "user-1",
      email: "a@b.com",
      full_name: "A",
      avatar_url: null,
      role: "student",
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:00Z",
    })

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    )

    expect(authHandler).not.toBeNull()
    await act(async () => {
      authHandler!("INITIAL_SESSION", makeSession(makeSupabaseUser()))
    })

    await waitFor(() => {
      expect(screen.getByTestId("loading").textContent).toBe("false")
      expect(screen.getByTestId("user").textContent).toBe("a@b.com")
    })
  })

  it("clears loading on INITIAL_SESSION even when there is no session", async () => {
    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    )
    await act(async () => {
      authHandler!("INITIAL_SESSION", null)
    })

    await waitFor(() => {
      expect(screen.getByTestId("loading").textContent).toBe("false")
    })
    expect(screen.getByTestId("user").textContent).toBe("anon")
  })

  it("updates the user on SIGNED_IN and then enriches from the profile row", async () => {
    const { single } = mockProfileFetch({
      id: "user-1",
      email: "a@b.com",
      full_name: "Teacher Tom",
      avatar_url: null,
      role: "teacher",
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-02T00:00:00Z",
    })

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    )

    await act(async () => {
      authHandler!("SIGNED_IN", makeSession(makeSupabaseUser()))
    })

    await waitFor(() => {
      expect(screen.getByTestId("user").textContent).toBe("a@b.com")
      expect(screen.getByTestId("role").textContent).toBe("teacher")
    })
    expect(single).toHaveBeenCalledTimes(1)
  })

  it("wipes the user on SIGNED_OUT", async () => {
    mockProfileFetch({
      id: "user-1",
      email: "a@b.com",
      full_name: "A",
      avatar_url: null,
      role: "student",
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:00Z",
    })

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    )

    await act(async () => {
      authHandler!("SIGNED_IN", makeSession(makeSupabaseUser()))
    })
    await waitFor(() => {
      expect(screen.getByTestId("user").textContent).toBe("a@b.com")
    })

    await act(async () => {
      authHandler!("SIGNED_OUT", null)
    })
    expect(screen.getByTestId("user").textContent).toBe("anon")
  })

  it("logout() calls authService.logout and clears state even on error", async () => {
    mockProfileFetch({
      id: "user-1",
      email: "a@b.com",
      full_name: "A",
      avatar_url: null,
      role: "student",
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:00Z",
    })
    logout.mockRejectedValue(new Error("boom"))

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    )
    await act(async () => {
      authHandler!("SIGNED_IN", makeSession(makeSupabaseUser()))
    })
    await waitFor(() => {
      expect(screen.getByTestId("user").textContent).toBe("a@b.com")
    })

    const user = screen.getByRole("button", { name: /sign out/i })
    await act(async () => {
      user.click()
    })

    expect(logout).toHaveBeenCalledTimes(1)
    await waitFor(() => {
      expect(screen.getByTestId("user").textContent).toBe("anon")
    })
  })

  it("ignores a stale profile response if the user has since changed", async () => {
    // Arrange two profile fetches: the first resolves slowly and would set
    // a stale teacher role; the second fires immediately and must win.
    let firstResolve: ((v: unknown) => void) | null = null
    const slowSingle = vi.fn(
      () =>
        new Promise((resolve) => {
          firstResolve = resolve as (v: unknown) => void
        }),
    )
    const fastSingle = vi.fn().mockResolvedValue({
      data: {
        id: "user-2",
        email: "b@b.com",
        full_name: "B",
        avatar_url: null,
        role: "student",
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
      },
      error: null,
    })
    from
      .mockReturnValueOnce({
        select: () => ({ eq: () => ({ single: slowSingle }) }),
      })
      .mockReturnValueOnce({
        select: () => ({ eq: () => ({ single: fastSingle }) }),
      })

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    )

    await act(async () => {
      authHandler!(
        "SIGNED_IN",
        makeSession(makeSupabaseUser({ id: "user-1", email: "a@b.com" })),
      )
    })
    await act(async () => {
      authHandler!(
        "SIGNED_IN",
        makeSession(makeSupabaseUser({ id: "user-2", email: "b@b.com" })),
      )
    })

    await waitFor(() => {
      expect(screen.getByTestId("user").textContent).toBe("b@b.com")
      expect(screen.getByTestId("role").textContent).toBe("student")
    })

    // Now let the stale response land. It must NOT overwrite state.
    await act(async () => {
      firstResolve!({
        data: {
          id: "user-1",
          email: "a@b.com",
          full_name: "A",
          avatar_url: null,
          role: "teacher",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        error: null,
      })
    })

    expect(screen.getByTestId("user").textContent).toBe("b@b.com")
    expect(screen.getByTestId("role").textContent).toBe("student")
  })
})
