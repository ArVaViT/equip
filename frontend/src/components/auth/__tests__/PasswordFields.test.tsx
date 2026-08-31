/**
 * One password form, three screens.
 *
 * Register, accept-invite and reset-password were three copies of the same
 * markup, and that is how they came to disagree with the server: all three
 * asked for six characters while Supabase Auth enforced twelve plus a breach
 * check. The first fix here touched only register — which would have left an
 * invited teacher and anybody resetting a password facing the same silent
 * wall. Hence the sentinel at the bottom.
 */
import type { ReactNode } from "react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";

import i18n from "@/i18n/config";
import { axe } from "@/test/a11y";
import { PasswordFields } from "@/components/auth/PasswordFields";

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>;
}

const BASE = {
  password: "",
  confirmPassword: "",
  idPrefix: "test",
  showPassword: false,
  passwordGenerated: false,
  onChange: vi.fn(),
  onToggleShowPassword: vi.fn(),
  onGeneratePassword: vi.fn(),
};

describe("PasswordFields", () => {
  it("states the rules and offers the generator", () => {
    render(
      <Wrapper>
        <PasswordFields {...BASE} />
      </Wrapper>,
    );
    expect(screen.getByText(i18n.t("auth.passwordPolicy.leakedNote"))).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: i18n.t("auth.passwordPolicy.generate") }),
    ).toBeInTheDocument();
  });

  it("reveals both fields together", () => {
    const { rerender } = render(
      <Wrapper>
        <PasswordFields {...BASE} showPassword />
      </Wrapper>,
    );
    const revealed = screen.getAllByRole("textbox");
    expect(revealed).toHaveLength(2);

    rerender(
      <Wrapper>
        <PasswordFields {...BASE} />
      </Wrapper>,
    );
    expect(screen.queryAllByRole("textbox")).toHaveLength(0);
  });

  it("keeps ids apart so two forms could share a page", () => {
    render(
      <Wrapper>
        <PasswordFields {...BASE} idPrefix="invite" passwordError="нет" />
      </Wrapper>,
    );
    const field = screen.getByLabelText(i18n.t("auth.password"));
    expect(field.getAttribute("aria-describedby")).toBe(
      "invite-password-error invite-password-requirements",
    );
  });

  it("lets a screen keep its own wording", () => {
    render(
      <Wrapper>
        <PasswordFields {...BASE} passwordLabel="Новый пароль" confirmLabel="Ещё раз" />
      </Wrapper>,
    );
    expect(screen.getByLabelText("Новый пароль")).toBeInTheDocument();
    expect(screen.getByLabelText("Ещё раз")).toBeInTheDocument();
  });

  it("asks for a generated password when the button is pressed", async () => {
    const onGeneratePassword = vi.fn();
    render(
      <Wrapper>
        <PasswordFields {...BASE} onGeneratePassword={onGeneratePassword} />
      </Wrapper>,
    );
    await userEvent.click(
      screen.getByRole("button", { name: i18n.t("auth.passwordPolicy.generate") }),
    );
    expect(onGeneratePassword).toHaveBeenCalledOnce();
  });

  it("has no accessibility violations", async () => {
    const { container } = render(
      <Wrapper>
        <PasswordFields {...BASE} password="short" confirmPassword="other" passwordError="нет" />
      </Wrapper>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("every screen that sets a password uses it", () => {
  const SCREENS = [
    "src/pages/Auth/register/RegisterForm.tsx",
    "src/pages/Invite/AcceptInvite.tsx",
    "src/pages/Auth/ResetPassword.tsx",
  ];

  for (const path of SCREENS) {
    it(`${path.split("/").pop()} does not hand-roll its own password inputs`, () => {
      const code = readFileSync(resolve(process.cwd(), path), "utf8");
      expect(code).toContain("PasswordFields");
      // A hand-rolled `type="password"` is a screen that will not learn about
      // the next rule change — exactly how these three drifted apart before.
      expect(code).not.toContain('type="password"');
    });
  }
});
