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
import { beforeEach, describe, it, expect, vi } from "vitest";
import { render, screen, renderHook, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router-dom";

import i18n from "@/i18n/config";
import { RegisterForm } from "@/pages/Auth/register/RegisterForm";
import { useRegister } from "@/pages/Auth/register/useRegister";
import { isLongEnough } from "@/lib/passwordPolicy";

const register = vi.fn();
vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({ register, signInWithGoogle: vi.fn() }),
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
  form: { full_name: "", email: "", password: "" },
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
    expect(field.getAttribute("aria-describedby")).toContain("password-rule");
  });

  it("asks for the password once, masked until asked to show it", () => {
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
    expect(screen.getByLabelText(i18n.t("auth.password"))).toHaveAttribute("type", "text");
    expect(screen.getAllByRole("textbox")).toHaveLength(3); // name, email, password
  });

  it("carries no age banner — the age is part of the consent, not the form", () => {
    const { container } = render(
      <Wrapper>
        <RegisterForm {...BASE_PROPS} />
      </Wrapper>,
    );
    expect(container.textContent).not.toMatch(/16/);
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
  it("fills the field with an acceptable value and shows it", () => {
    const { result } = renderHook(() => useRegister());

    act(() => {
      result.current.handleGeneratePassword();
    });

    expect(isLongEnough(result.current.form.password)).toBe(true);
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

describe("useRegister — after the form", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    register.mockReset();
  });

  async function submit(result: { current: ReturnType<typeof useRegister> }) {
    act(() => {
      result.current.handleChange("full_name", "Sasha Petrov");
      result.current.handleChange("email", "  sasha@web.de ");
      result.current.handleChange("password", "a long enough passphrase");
    });
    await act(() => result.current.handleSubmit());
  }

  it("sends the address trimmed, and the mail screen survives a reload", async () => {
    register.mockResolvedValue({ userId: "u1", repeated: false });
    const { result } = renderHook(() => useRegister());
    await submit(result);

    expect(register.mock.calls[0]?.[0]).toBe("sasha@web.de");
    expect(result.current.sent).toEqual({ email: "sasha@web.de", repeated: false });
    const reloaded = renderHook(() => useRegister());
    expect(reloaded.result.current.sent).toEqual({ email: "sasha@web.de", repeated: false });
  });

  it("remembers that the address was registered before", async () => {
    register.mockResolvedValue({ userId: "u1", repeated: true });
    const { result } = renderHook(() => useRegister());
    await submit(result);
    expect(result.current.sent?.repeated).toBe(true);
  });

  it("goes back to the form with the address to correct", async () => {
    register.mockResolvedValue({ userId: "u1", repeated: false });
    const { result } = renderHook(() => useRegister());
    await submit(result);

    act(() => result.current.changeAddress());

    expect(result.current.sent).toBeNull();
    expect(result.current.form.email).toBe("sasha@web.de");
    expect(window.sessionStorage.getItem("equip:signupSent")).toBeNull();
  });
});
