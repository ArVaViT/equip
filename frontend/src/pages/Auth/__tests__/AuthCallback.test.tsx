/**
 * What happens when somebody clicks a confirmation link that no longer works.
 *
 * `/auth/v1/verify` does not refuse a stale token — it redirects to the site
 * with the reason in the fragment. Before this, such an arrival was
 * indistinguishable from a slow OAuth round-trip: a spinner, fifteen
 * seconds, then a generic failure. The one thing the person could have done
 * — ask for a new link — was never mentioned.
 */
import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router-dom";

import i18n from "@/i18n/config";
import AuthCallback from "@/pages/Auth/AuthCallback";

const unsubscribe = vi.fn();
vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe } } }),
    },
  },
}));

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  );
}

function withHash(hash: string) {
  window.location.hash = hash;
}

describe("AuthCallback", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    window.location.hash = "";
  });

  afterEach(() => {
    vi.useRealTimers();
    window.location.hash = "";
  });

  it("says the link expired instead of spinning", () => {
    withHash("#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid");
    render(
      <Wrapper>
        <AuthCallback />
      </Wrapper>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(i18n.t("auth.errors.linkExpired"));
    // And offers the way out, rather than leaving the person on a dead page.
    expect(screen.getByRole("link", { name: i18n.t("auth.signIn") })).toBeInTheDocument();
  });

  it("reports an unfamiliar failure without pretending it is an expiry", () => {
    withHash("#error_code=server_error&error_description=whatever");
    render(
      <Wrapper>
        <AuthCallback />
      </Wrapper>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(i18n.t("auth.callback.timedOut"));
  });

  it("still waits for the session on a normal arrival", () => {
    render(
      <Wrapper>
        <AuthCallback />
      </Wrapper>,
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText(i18n.t("auth.callback.completing"))).toBeInTheDocument();
  });
});
