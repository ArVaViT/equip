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

// Augment Vitest's Matchers shape so ``expect(...).toHaveNoViolations()``
// type-checks alongside ``.toBe`` / ``.toEqual``. `Matchers` (rather than
// `Assertion`, which vitest itself declares more than once internally with
// mismatched type parameters) is the one interface vitest defines exactly
// once, so it is the only augmentation target TS can merge cleanly with.
declare module "vitest" {
  // The `T` parameter must stay to match vitest's own arity exactly (see
  // above); the matcher itself doesn't need it.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface Matchers<R = void | Promise<void>, T = unknown> {
    toHaveNoViolations(): R;
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
