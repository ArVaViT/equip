/**
 * Feature-level a11y audits.
 *
 * The ``ui/__tests__/a11y*.test.tsx`` files cover primitive layers
 * (Button, Card, Badge, Dialog, etc.); this file zooms out to the
 * feature components a student or teacher actually sees: welcome
 * card, error / empty states, page header, stat card. If any of
 * these regresses past WCAG 2.1 AA, the regression shows up in CI
 * not in a manual audit.
 *
 * Components that pull in AuthProvider / heavier provider stacks
 * (TodayCard, Footer with its full nav, FirstRunFlow) belong in the
 * existing per-component test files alongside the harness those
 * tests already build — folding axe into those tests is the right
 * follow-up. This file restricts itself to pure presentational
 * components.
 */
import type { ReactNode } from "react";
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { I18nextProvider } from "react-i18next";
import { Users } from "lucide-react";

import i18n from "@/i18n/config";
import { axe } from "@/test/a11y";
import { WelcomeCard } from "@/components/dashboard/WelcomeCard";
import { EmptyState } from "@/components/patterns/EmptyState";
import { ErrorState } from "@/components/patterns/ErrorState";
import { PageHeader } from "@/components/patterns/PageHeader";
import { StatCard } from "@/components/patterns/StatCard";

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  );
}

describe("a11y — feature components", () => {
  it("WelcomeCard (full prop shape) has no violations", async () => {
    const { container } = render(
      <WelcomeCard
        eyebrow="Welcome"
        title="Welcome to Equip"
        description="A short intro so the page has a meaningful landmark."
      />,
      { wrapper: Wrapper },
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("EmptyState (with action) has no violations", async () => {
    const { container } = render(
      <EmptyState
        title="No courses yet"
        description="Create your first course to get started."
        action={<a href="/teacher/courses/new">Create course</a>}
      />,
      { wrapper: Wrapper },
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("ErrorState (with retry) has no violations", async () => {
    const { container } = render(
      <ErrorState
        title="Couldn't load courses"
        description="Check your connection and try again."
        action={<button>Retry</button>}
      />,
      { wrapper: Wrapper },
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("PageHeader (title + description + meta) has no violations", async () => {
    const { container } = render(
      <PageHeader
        title={<h1>All courses</h1>}
        description="Catalog of published courses."
        meta={<span>42 courses</span>}
      />,
      { wrapper: Wrapper },
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("StatCard (value-leading) has no violations", async () => {
    const { container } = render(
      <StatCard label="Active students" value={128} icon={Users} />,
      { wrapper: Wrapper },
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("StatCard (icon-leading) has no violations", async () => {
    const { container } = render(
      <StatCard
        label="Active students"
        value={128}
        icon={Users}
        variant="icon-leading"
      />,
      { wrapper: Wrapper },
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
