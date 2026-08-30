/**
 * The signup password path, end to end through the hook and the form.
 *
 * Six of the seven accounts ever created with a password on this platform
 * never confirmed, and the auth log for 2026-08-30 shows the last of them
 * refused three times for a weak password before getting in. The rules were
 * never stated; there was no way to satisfy them except by guessing. These
 * tests cover the two things that changed: the rules are shown, and there is
 * a way to not have to invent one.
 */
import type { ReactNode } from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, renderHook, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router-dom";

import i18n from "@/i18n/config";
import { RegisterForm } from "@/pages/Auth/register/RegisterForm";
import { useRegister } from "@/pages/Auth/register/useRegister";
import { passwordMeetsLocalRules } from "@/lib/passwordPolicy";

vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({ register: vi.fn(), signInWithGoogle: vi.fn() }),
}));

// AuthLayout reads the theme for its own chrome; the password affordances
// under test do not care which theme is active.
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

const BASE_PROPS = {
  form: { full_name: "", email: "", password: "", confirmPassword: "" },
  errors: {},
  serverError: "",
  loading: false,
  googleLoading: false,
  showPassword: false,
  passwordGenerated: false,
  onChange: vi.fn(),
  onSubmit: vi.fn(),
  onGoogleSignUp: vi.fn(),
  onToggleShowPassword: vi.fn(),
  onGeneratePassword: vi.fn(),
};

describe("RegisterForm — password affordances", () => {
  it("points the password field at the rules for screen readers", () => {
    render(
      <Wrapper>
        <RegisterForm {...BASE_PROPS} />
      </Wrapper>,
    );
    const field = screen.getByLabelText(i18n.t("auth.password"));
    expect(field.getAttribute("aria-describedby")).toContain("password-requirements");
  });

  it("keeps both fields masked until asked, then reveals both together", () => {
    const { rerender } = render(
      <Wrapper>
        <RegisterForm {...BASE_PROPS} />
      </Wrapper>,
    );
    expect(screen.getByLabelText(i18n.t("auth.password"))).toHaveAttribute("type", "password");

    rerender(
      <Wrapper>
        <RegisterForm {...BASE_PROPS} showPassword />
      </Wrapper>,
    );
    // Both, not just the first: a revealed password beside a masked
    // confirmation is a field you still cannot check by eye.
    expect(screen.getByLabelText(i18n.t("auth.password"))).toHaveAttribute("type", "text");
    expect(
      screen.getByLabelText(i18n.t("authRegister.confirmPasswordShort")),
    ).toHaveAttribute("type", "text");
  });

  it("offers a way out of inventing a password", async () => {
    const onGeneratePassword = vi.fn();
    render(
      <Wrapper>
        <RegisterForm {...BASE_PROPS} onGeneratePassword={onGeneratePassword} />
      </Wrapper>,
    );
    await userEvent.click(
      screen.getByRole("button", { name: i18n.t("auth.passwordPolicy.generate") }),
    );
    expect(onGeneratePassword).toHaveBeenCalledOnce();
  });
});

describe("useRegister — generated password", () => {
  it("fills both fields with the same acceptable value and shows it", () => {
    const { result } = renderHook(() => useRegister());

    act(() => {
      result.current.handleGeneratePassword();
    });

    const { password, confirmPassword } = result.current.form;
    expect(password).not.toBe("");
    // Filling only `password` would hand the person a "passwords do not
    // match" error for a password they never typed.
    expect(confirmPassword).toBe(password);
    expect(passwordMeetsLocalRules(password, confirmPassword)).toBe(true);
    expect(result.current.showPassword).toBe(true);
    expect(result.current.passwordGenerated).toBe(true);
  });

  it("drops the save-it note once the person edits the password", () => {
    const { result } = renderHook(() => useRegister());

    act(() => {
      result.current.handleGeneratePassword();
    });
    expect(result.current.passwordGenerated).toBe(true);

    act(() => {
      result.current.handleChange("password", "typed over it");
    });
    expect(result.current.passwordGenerated).toBe(false);
  });
});
