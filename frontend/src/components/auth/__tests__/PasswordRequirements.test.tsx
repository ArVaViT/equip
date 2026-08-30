/**
 * The rules the form now states out loud.
 *
 * Before this component existed the server enforced twelve characters and a
 * breach check while the form asked for six and mentioned neither, so the
 * only way to learn a rule was to break it. These tests hold the two halves
 * together: what is shown, and what is ticked.
 */
import type { ReactNode } from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";

import i18n from "@/i18n/config";
import { axe } from "@/test/a11y";
import { PasswordRequirements } from "@/components/auth/PasswordRequirements";
import { PASSWORD_MIN_LENGTH } from "@/lib/passwordPolicy";

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>;
}

const LONG_ENOUGH = "a".repeat(PASSWORD_MIN_LENGTH);

describe("PasswordRequirements", () => {
  it("states the length rule before anything is typed", () => {
    render(
      <Wrapper>
        <PasswordRequirements password="" confirmPassword="" />
      </Wrapper>,
    );
    expect(screen.getByText(new RegExp(String(PASSWORD_MIN_LENGTH)))).toBeInTheDocument();
  });

  it("says the breach check happens on submit rather than ticking it", () => {
    render(
      <Wrapper>
        <PasswordRequirements password={LONG_ENOUGH} confirmPassword={LONG_ENOUGH} />
      </Wrapper>,
    );
    // The note is present, and it is NOT one of the tickable rules: a browser
    // cannot answer Have I Been Pwned, so no row may claim it passed.
    expect(screen.getByText(i18n.t("auth.passwordPolicy.leakedNote"))).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("marks each rule met or unmet in text, not colour alone", () => {
    const { rerender } = render(
      <Wrapper>
        <PasswordRequirements password="short" confirmPassword="" />
      </Wrapper>,
    );
    expect(screen.getAllByText(i18n.t("auth.passwordPolicy.ruleNotMet"))).toHaveLength(2);

    rerender(
      <Wrapper>
        <PasswordRequirements password={LONG_ENOUGH} confirmPassword={LONG_ENOUGH} />
      </Wrapper>,
    );
    expect(screen.getAllByText(i18n.t("auth.passwordPolicy.ruleMet"))).toHaveLength(2);
  });

  it("has no accessibility violations", async () => {
    const { container } = render(
      <Wrapper>
        <PasswordRequirements password={LONG_ENOUGH} confirmPassword="" />
      </Wrapper>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
