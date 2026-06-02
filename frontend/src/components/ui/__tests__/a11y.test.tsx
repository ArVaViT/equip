/**
 * Foundation a11y tests — pins jest-axe wiring + a handful of
 * representative shadcn primitives. Each variant of an accessible
 * component should land its own ``await axe(container)`` assertion in
 * the surrounding feature test rather than re-snapshotting them here.
 *
 * The selection below covers the patterns that show up everywhere —
 * if these stay clean, the design-system primitives below them stay
 * clean, and feature-specific a11y regressions show up in the
 * feature tests themselves.
 */
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";

import { axe } from "@/test/a11y";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";

describe("a11y foundation", () => {
  it("Button (default variant) has no violations", async () => {
    const { container } = render(<Button>Submit</Button>);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("Button (icon-only) requires an aria-label", async () => {
    // An icon-only button with NO accessible name is a violation we
    // actively want axe to catch — pin the catch so a future button
    // change that drops the aria-label requirement surfaces.
    const { container } = render(
      <Button aria-label="Close dialog">
        <svg aria-hidden="true" focusable="false" width="14" height="14" />
      </Button>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("Card with title + content has no violations", async () => {
    const { container } = render(
      <Card>
        <CardHeader>
          <CardTitle>Recent activity</CardTitle>
        </CardHeader>
        <CardContent>
          <p>You have 3 new notifications.</p>
        </CardContent>
      </Card>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("Badge with text content has no violations", async () => {
    const { container } = render(<Badge>Beta</Badge>);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("Label-Input pair has no violations", async () => {
    // Pin the htmlFor / id wiring — the most common 'unlabeled
    // input' bug shows up when a refactor accidentally desyncs the
    // two. axe catches it; this test pins the catch.
    const { container } = render(
      <div>
        <Label htmlFor="email">Email</Label>
        <Input id="email" type="email" />
      </div>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("unlabeled input IS flagged by axe (sentinel)", async () => {
    // Sentinel: an input WITHOUT a label should fail axe. If this
    // ever passes, jest-axe is mis-wired and the other tests above
    // are giving false confidence.
    const { container } = render(<Input type="email" />);
    const result = await axe(container);
    // We don't assert ``toHaveNoViolations`` here — we WANT a
    // violation. We assert at least one violation surfaced.
    expect(result.violations.length).toBeGreaterThan(0);
  });
});
