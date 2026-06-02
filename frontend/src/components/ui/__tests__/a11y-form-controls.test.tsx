/**
 * Component-level a11y coverage for form-control primitives.
 *
 * Companion to ``a11y-overlays.test.tsx``. Pins:
 *   - Checkbox with associated <Label>.
 *   - RadioGroup with multiple items + group label.
 *   - Select (Radix) with associated <Label>.
 *   - Textarea with associated <Label>.
 *
 * The pattern that breaks most often is the htmlFor/id pair getting
 * desynced when a field is renamed. axe catches it; this test pins
 * the catch so the regression surfaces in CI not in QA.
 */
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";

import { axe } from "@/test/a11y";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

describe("a11y — form-control primitives", () => {
  it("Checkbox paired with Label has no violations", async () => {
    const { container } = render(
      <div className="flex items-center gap-2">
        <Checkbox id="terms" />
        <Label htmlFor="terms">I agree to the terms</Label>
      </div>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("RadioGroup with labelled options has no violations", async () => {
    const { container } = render(
      <fieldset>
        <legend>Difficulty</legend>
        <RadioGroup defaultValue="easy">
          <div>
            <RadioGroupItem id="r-easy" value="easy" />
            <Label htmlFor="r-easy">Easy</Label>
          </div>
          <div>
            <RadioGroupItem id="r-medium" value="medium" />
            <Label htmlFor="r-medium">Medium</Label>
          </div>
          <div>
            <RadioGroupItem id="r-hard" value="hard" />
            <Label htmlFor="r-hard">Hard</Label>
          </div>
        </RadioGroup>
      </fieldset>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("Select with associated Label has no violations", async () => {
    const { baseElement } = render(
      <div>
        <Label htmlFor="locale">Locale</Label>
        <Select>
          <SelectTrigger id="locale">
            <SelectValue placeholder="Pick a locale" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="en">English</SelectItem>
            <SelectItem value="ru">Russian</SelectItem>
          </SelectContent>
        </Select>
      </div>,
    );
    expect(await axe(baseElement)).toHaveNoViolations();
  });

  it("Textarea with associated Label has no violations", async () => {
    const { container } = render(
      <div>
        <Label htmlFor="bio">About you</Label>
        <Textarea id="bio" placeholder="A few sentences..." />
      </div>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("Checkbox WITHOUT a label IS flagged (sentinel)", async () => {
    // Mirror of the unlabeled-input sentinel in ``a11y.test.tsx`` —
    // proves the form-control rules are actually firing on this
    // primitive set.
    const { container } = render(<Checkbox id="orphan" />);
    const result = await axe(container);
    expect(result.violations.length).toBeGreaterThan(0);
  });
});
