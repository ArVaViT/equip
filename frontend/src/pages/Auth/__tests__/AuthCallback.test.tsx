/**
 * The page Google and email links land on, once `main.tsx` has taken the code
 * or token out of the URL.
 *
 * A spent or stale link does not sign anybody in, and before this page named
 * that, such an arrival was indistinguishable from a slow OAuth round-trip:
 * a spinner, fifteen seconds, then a generic failure. The one thing the
 * person could have done — ask for a new link — was never mentioned.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import i18n from "@/i18n/config";
import AuthCallback from "@/pages/Auth/AuthCallback";
import type { AuthLandingResult } from "@/lib/authLanding";

const completeAuthLanding = vi.fn<() => Promise<AuthLandingResult>>();
vi.mock("@/lib/authLanding", () => ({
  completeAuthLanding: () => completeAuthLanding(),
}));

const getSession = vi.fn();
vi.mock("@/lib/supabase", () => ({
  supabase: { auth: { getSession: () => getSession() } },
}));

function renderAt(path = "/auth/callback") {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route path="/auth/confirm" element={<AuthCallback />} />
          <Route path="/" element={<p>dashboard</p>} />
          <Route path="/auth/reset-password" element={<p>reset form</p>} />
          <Route path="/login" element={<p>login page</p>} />
        </Routes>
      </MemoryRouter>
    </I18nextProvider>,
  );
}

describe("AuthCallback", () => {
  beforeEach(() => {
    completeAuthLanding.mockReset();
    getSession.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("goes to the dashboard once the link signed the person in", async () => {
    completeAuthLanding.mockResolvedValue({ status: "signed-in", recovery: false });
    renderAt("/auth/confirm");
    expect(await screen.findByText("dashboard")).toBeInTheDocument();
  });

  it("sends a recovery sign-in to the page that sets a new password", async () => {
    completeAuthLanding.mockResolvedValue({ status: "signed-in", recovery: true });
    renderAt();
    expect(await screen.findByText("reset form")).toBeInTheDocument();
  });

  it("says the link expired instead of spinning", async () => {
    completeAuthLanding.mockResolvedValue({ status: "failed", reason: "expired" });
    renderAt("/auth/confirm");
    expect(await screen.findByRole("alert")).toHaveTextContent(i18n.t("auth.errors.linkExpired"));
    // And offers the way out, rather than leaving the person on a dead page.
    expect(screen.getByRole("link", { name: i18n.t("auth.signIn") })).toBeInTheDocument();
  });

  it("reports an unfamiliar failure without pretending it is an expiry", async () => {
    completeAuthLanding.mockResolvedValue({ status: "failed", reason: "other" });
    renderAt();
    expect(await screen.findByRole("alert")).toHaveTextContent(i18n.t("auth.callback.timedOut"));
  });

  it("shows progress while the link is being verified", () => {
    completeAuthLanding.mockReturnValue(new Promise(() => {}));
    renderAt();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText(i18n.t("auth.callback.completing"))).toBeInTheDocument();
  });

  it("treats a reload after success as success", async () => {
    completeAuthLanding.mockResolvedValue({ status: "nothing" });
    getSession.mockResolvedValue({ data: { session: { user: { id: "u1" } } } });
    renderAt();
    expect(await screen.findByText("dashboard")).toBeInTheDocument();
  });

  it("sends a bare visit with no session back to sign-in", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    completeAuthLanding.mockResolvedValue({ status: "nothing" });
    getSession.mockResolvedValue({ data: { session: null } });
    renderAt();
    expect(await screen.findByText(i18n.t("auth.callback.timedOut"))).toBeInTheDocument();
    await vi.advanceTimersByTimeAsync(3100);
    await waitFor(() => expect(screen.getByText("login page")).toBeInTheDocument());
  });
});
