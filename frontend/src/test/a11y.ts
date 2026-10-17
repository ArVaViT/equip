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

/**
 * The page's headings as levels, in document order, and every place the
 * outline skips a level going down (h1 → h3) — axe's `heading-order` in a
 * form a test can name. Going back up any distance is fine; going down
 * more than one step is not. The first heading is the baseline, so a
 * component rendered alone (a quiz whose h2 sits under the lesson's h1)
 * can be checked too; a page test asserts its one h1 separately.
 */
export function headingOutline(container: HTMLElement): { levels: number[]; gaps: string[] } {
  const headings = Array.from(container.querySelectorAll<HTMLElement>("h1, h2, h3, h4, h5, h6"))
  const levels = headings.map((h) => Number(h.tagName[1]))
  const gaps: string[] = []
  for (let i = 1; i < headings.length; i++) {
    const previous = levels[i - 1] ?? 0
    const level = levels[i] ?? 0
    if (level > previous + 1) {
      gaps.push(`h${previous} → h${level} «${headings[i]?.textContent?.trim() ?? ""}»`)
    }
  }
  return { levels, gaps }
}
