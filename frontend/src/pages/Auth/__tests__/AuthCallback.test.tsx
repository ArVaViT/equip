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
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

const sendSignInLink = vi.fn();
vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ sendSignInLink }) }));
vi.mock("@/context/useTheme", () => ({
  useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }),
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
    getSession.mockResolvedValue({ data: { session: null } });
    sendSignInLink.mockReset();
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

  it("says the link expired and offers a new one on the spot", async () => {
    const user = userEvent.setup();
    completeAuthLanding.mockResolvedValue({ status: "failed", reason: "expired" });
    sendSignInLink.mockResolvedValue(undefined);
    renderAt("/auth/confirm");
    expect(await screen.findByRole("alert")).toHaveTextContent(i18n.t("auth.errors.linkExpired"));

    await user.type(screen.getByLabelText(i18n.t("auth.email")), " sasha@web.de ");
    await user.click(screen.getByRole("button", { name: i18n.t("auth.sendNewLink") }));

    expect(sendSignInLink).toHaveBeenCalledWith("sasha@web.de");
    expect(await screen.findByRole("status")).toHaveTextContent(i18n.t("auth.signInLinkSent"));
  });

  it("takes a spent link opened in the browser it already signed in as success", async () => {
    completeAuthLanding.mockResolvedValue({ status: "failed", reason: "expired" });
    getSession.mockResolvedValue({ data: { session: { user: { id: "u1" } } } });
    renderAt("/auth/confirm");
    expect(await screen.findByText("dashboard")).toBeInTheDocument();
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

  it("leaves a bare visit with no session where it is, with a way to sign in", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    completeAuthLanding.mockResolvedValue({ status: "nothing" });
    renderAt();
    expect(await screen.findByText(i18n.t("auth.callback.timedOut"))).toBeInTheDocument();
    await vi.advanceTimersByTimeAsync(5000);
    expect(screen.queryByText("login page")).toBeNull();
    expect(screen.getByRole("link", { name: i18n.t("auth.signIn") })).toHaveAttribute("href", "/login");
  });
});
