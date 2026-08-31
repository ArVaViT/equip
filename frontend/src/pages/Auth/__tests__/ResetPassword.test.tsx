/**
 * The page somebody lands on after clicking "reset password".
 *
 * Two defects met here. The link used to land on `/auth/confirm`, which
 * signs a person in and sends them to the dashboard — so whoever had
 * forgotten their password ended up inside their account with no way to set
 * a new one. And this page, reached without a live recovery session, showed
 * the form anyway, took a new password, and answered with GoTrue's "Auth
 * session missing".
 */
import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router-dom";

import i18n from "@/i18n/config";
import ResetPassword from "@/pages/Auth/ResetPassword";

const getSession = vi.fn();
const unsubscribe = vi.fn();
vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: () => getSession(),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe } } }),
    },
  },
}));
vi.mock("@/services/auth", () => ({ authService: { updatePassword: vi.fn() } }));

// AuthLayout reads the theme for its own chrome; irrelevant to what is tested.
vi.mock("@/context/useTheme", () => ({
  useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }),
}));

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  );
}

describe("ResetPassword", () => {
  beforeEach(() => {
    getSession.mockReset();
  });

  it("shows the form once the recovery session is there", async () => {
    getSession.mockResolvedValue({ data: { session: { user: { id: "u1" } } } });
    render(
      <Wrapper>
        <ResetPassword />
      </Wrapper>,
    );
    await waitFor(() =>
      expect(screen.getByLabelText(i18n.t("auth.resetPassword.newPassword"))).toBeInTheDocument(),
    );
    // And the rules are stated here too, not only on register.
    expect(screen.getByText(i18n.t("auth.passwordPolicy.leakedNote"))).toBeInTheDocument();
  });

  it("does not offer the form without a session", async () => {
    vi.useFakeTimers();
    getSession.mockResolvedValue({ data: { session: null } });
    render(
      <Wrapper>
        <ResetPassword />
      </Wrapper>,
    );

    // A miss is only a miss after the client has had time to parse the
    // fragment, so the page waits before saying anything.
    expect(screen.queryByRole("alert")).toBeNull();

    await vi.advanceTimersByTimeAsync(4100);
    expect(screen.getByRole("alert")).toHaveTextContent(i18n.t("auth.errors.linkExpired"));
    expect(
      screen.getByRole("link", { name: i18n.t("auth.forgotPassword.submit") }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText(i18n.t("auth.resetPassword.newPassword"))).toBeNull();
    vi.useRealTimers();
  });
});
