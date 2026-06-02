/**
 * jest-axe glue for Vitest.
 *
 * Usage in any component test:
 *
 *   import { axe } from "@/test/a11y";
 *   const { container } = render(<MyButton>label</MyButton>);
 *   expect(await axe(container)).toHaveNoViolations();
 *
 * Rule customisation: `axe` is preconfigured to skip a handful of rules
 * that don't make sense inside an isolated component test (e.g.
 * `region` — there's no page landmark in a single-component snapshot).
 * Add new exceptions VERY sparingly and only with a comment explaining
 * why the rule cannot pass in this context.
 */
import { configureAxe, toHaveNoViolations } from "jest-axe";
import { expect } from "vitest";

expect.extend(toHaveNoViolations);

// Augment Vitest's Assertion shape so ``expect(...).toHaveNoViolations()``
// type-checks alongside ``.toBe`` / ``.toEqual``.
declare module "vitest" {
  interface Assertion {
    toHaveNoViolations(): void;
  }
  interface AsymmetricMatchersContaining {
    toHaveNoViolations(): void;
  }
}

export const axe = configureAxe({
  rules: {
    // ``region`` flags any page that lacks a landmark; the unit-test
    // renders an isolated component, not a full page, so the rule is
    // irrelevant. The full-page Playwright suite catches missing
    // landmarks at the route level.
    region: { enabled: false },
    // ``page-has-heading-one`` is the same story — isolated component
    // tests don't render an h1.
    "page-has-heading-one": { enabled: false },
  },
});
