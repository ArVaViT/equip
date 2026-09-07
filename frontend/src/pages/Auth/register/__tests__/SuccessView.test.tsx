/**
 * The screen after "create account", which used to be a dead end.
 *
 * It said "check your email" and offered one button: back to sign in —
 * which is the one thing the person cannot do yet, because the account is
 * not confirmed. Six of the seven accounts ever created with a password on
 * this platform never confirmed. If the email did not arrive, the product
 * had nothing to say.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router-dom";

import i18n from "@/i18n/config";
import { SuccessView } from "@/pages/Auth/register/SuccessView";

const calls: string[] = [];
let behaviour: (email: string) => Promise<void> = async () => {};

vi.mock("@/services/auth", () => ({
  authService: {
    resendConfirmation: (email: string) => {
      calls.push(email);
      return behaviour(email);
    },
  },
}));

vi.mock("@/context/useTheme", () => ({
  useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }),
}));

function renderView() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <SuccessView email="someone@example.com" />
      </MemoryRouter>
    </I18nextProvider>,
  );
}

describe("SuccessView", () => {
  beforeEach(() => {
    calls.length = 0;
    behaviour = async () => {};
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("names the spam folder, where the email most often is", () => {
    renderView();
    expect(screen.getByText(i18n.t("authRegister.success.checkSpam"))).toBeInTheDocument();
  });

  it("does not offer a resend the server would refuse", () => {
    // Supabase allows one email per minute per address. Offering the button
    // immediately would spend the click on a 429 nobody can interpret.
    renderView();
    const button = screen.getByRole("button", { name: /59|60/ });
    expect(button).toBeDisabled();
  });

  it("offers the resend once the minute is up, and sends it", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderView();

    await vi.advanceTimersByTimeAsync(60_000);

    const button = await screen.findByRole("button", {
      name: new RegExp(i18n.t("authRegister.success.resend")),
    });
    expect(button).toBeEnabled();

    await user.click(button);
    await waitFor(() => expect(calls).toEqual(["someone@example.com"]));
    expect(await screen.findByText(i18n.t("authRegister.success.resent"))).toBeInTheDocument();
  });

  it("says what went wrong instead of pretending it sent", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    behaviour = async () => {
      throw new Error("rate limited");
    };
    renderView();
    await vi.advanceTimersByTimeAsync(60_000);

    await user.click(
      await screen.findByRole("button", {
        name: new RegExp(i18n.t("authRegister.success.resend")),
      }),
    );

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText(i18n.t("authRegister.success.resent"))).toBeNull();
  });
});
