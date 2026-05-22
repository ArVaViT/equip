import React from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { describe, it, expect, vi } from "vitest"

import i18n from "@/i18n/config"
import type {
  ReadinessAction,
  ReadinessCheck,
  ReadinessReport,
} from "@/services/courseReadiness"
import { CourseReadinessCard } from "@/pages/Teacher/editor/CourseReadinessCard"

/**
 * Component tests for ``CourseReadinessCard``. The card is the only
 * surface the editor reads readiness through, so its observable
 * contract is:
 *
 *   1. ``loading=true`` → render the skeleton (a11y-busy=true).
 *   2. ``report=null`` → render nothing (silently hide on backend blip).
 *   3. ``report`` provided → render the score, the summary line, and
 *      — once expanded — the failing checks grouped by severity, with
 *      a Fix button on those that carry an ``action``.
 *   4. Tone follows severity precedence: critical wins over
 *      recommended wins over success.
 *   5. ``onFix`` fires with the check's action when the Fix button is
 *      clicked.
 */

function Wrapper({ children }: { children: React.ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

const renderOpts = { wrapper: Wrapper }

function makeCheck(over: Partial<ReadinessCheck> = {}): ReadinessCheck {
  return {
    id: over.id ?? "courseReadiness.checks.hasDescription",
    severity: over.severity ?? "critical",
    passed: over.passed ?? false,
    message_key: over.message_key ?? "courseReadiness.checks.hasDescription",
    subject: over.subject ?? null,
    action: over.action ?? null,
  }
}

function makeReport(over: Partial<ReadinessReport> = {}): ReadinessReport {
  return {
    course_id: over.course_id ?? "c-1",
    total: over.total ?? 5,
    passing: over.passing ?? 4,
    critical_failing: over.critical_failing ?? 0,
    score: over.score ?? 80,
    checks: over.checks ?? [],
  }
}

describe("CourseReadinessCard", () => {
  it("renders the skeleton when loading", () => {
    const { container } = render(
      <CourseReadinessCard report={null} loading={true} />,
      renderOpts,
    )
    const section = container.querySelector('[aria-busy="true"]')
    expect(section).not.toBeNull()
  })

  it("renders nothing when report is null and not loading", () => {
    const { container } = render(
      <CourseReadinessCard report={null} loading={false} />,
      renderOpts,
    )
    expect(container.firstChild).toBeNull()
  })

  it("renders the all-passed message when every check is green", () => {
    const report = makeReport({
      passing: 5,
      total: 5,
      critical_failing: 0,
      score: 100,
      checks: [makeCheck({ passed: true, severity: "polish" })],
    })
    render(<CourseReadinessCard report={report} loading={false} />, renderOpts)
    expect(
      screen.getByText(/your course is ready to publish/i),
    ).toBeInTheDocument()
  })

  it("renders the failing-summary line and critical count when applicable", () => {
    const report = makeReport({
      passing: 3,
      total: 5,
      critical_failing: 2,
      score: 60,
      checks: [
        makeCheck({ id: "a", severity: "critical", passed: false }),
        makeCheck({ id: "b", severity: "critical", passed: false }),
        makeCheck({ id: "c", severity: "recommended", passed: true }),
      ],
    })
    render(<CourseReadinessCard report={report} loading={false} />, renderOpts)
    // Summary uses i18n interpolation; assert against the numeric
    // substrings the translation guarantees.
    expect(screen.getByText(/3.*5/)).toBeInTheDocument()
    // Critical-count line.
    expect(screen.getByText(/2.*critical/i)).toBeInTheDocument()
  })

  it("starts collapsed and expands when the header is clicked", async () => {
    const user = userEvent.setup()
    const report = makeReport({
      checks: [
        makeCheck({
          id: "open-1",
          severity: "critical",
          passed: false,
          message_key: "courseReadiness.checks.hasDescription",
        }),
      ],
    })
    render(<CourseReadinessCard report={report} loading={false} />, renderOpts)

    // Collapsed: the check's message must not be in the DOM yet.
    expect(
      screen.queryByText(/has a description for the catalog/i),
    ).not.toBeInTheDocument()

    const header = screen.getByRole("button", { expanded: false })
    await user.click(header)

    // Expanded: the check appears.
    expect(
      screen.getByText(/has a description for the catalog/i),
    ).toBeInTheDocument()
  })

  it("groups checks by severity in the canonical order", async () => {
    const user = userEvent.setup()
    const report = makeReport({
      checks: [
        makeCheck({
          id: "polish-1",
          severity: "polish",
          message_key: "courseReadiness.checks.hasMultipleModules",
        }),
        makeCheck({
          id: "crit-1",
          severity: "critical",
          message_key: "courseReadiness.checks.hasDescription",
        }),
        makeCheck({
          id: "rec-1",
          severity: "recommended",
          message_key: "courseReadiness.checks.hasEnrollmentWindow",
        }),
      ],
    })
    render(<CourseReadinessCard report={report} loading={false} />, renderOpts)
    await user.click(screen.getByRole("button", { expanded: false }))

    // Header order: critical → recommended → polish.
    const headers = screen.getAllByRole("heading", { level: 3 })
    expect(headers.map((h) => h.textContent?.toLowerCase())).toEqual([
      "critical",
      "recommended",
      "polish",
    ])
  })

  it("calls onFix with the check's action when Fix is clicked", async () => {
    const user = userEvent.setup()
    const onFix = vi.fn()
    const action: ReadinessAction = {
      type: "set_description",
      params: { course_id: "c-1" },
    }
    const check = makeCheck({
      id: "fixable",
      severity: "critical",
      passed: false,
      action,
      message_key: "courseReadiness.checks.hasDescription",
    })
    const report = makeReport({ checks: [check] })
    render(
      <CourseReadinessCard report={report} loading={false} onFix={onFix} />,
      renderOpts,
    )

    await user.click(screen.getByRole("button", { expanded: false }))
    const fixButton = screen.getByRole("button", { name: /fix/i })
    await user.click(fixButton)

    expect(onFix).toHaveBeenCalledTimes(1)
    expect(onFix).toHaveBeenCalledWith(action, check)
  })

  it("does NOT render a Fix button for passing checks", async () => {
    const user = userEvent.setup()
    const onFix = vi.fn()
    const action: ReadinessAction = {
      type: "set_description",
      params: { course_id: "c-1" },
    }
    const report = makeReport({
      checks: [
        makeCheck({
          id: "done",
          severity: "critical",
          passed: true,
          action,
          message_key: "courseReadiness.checks.hasDescription",
        }),
      ],
    })
    render(
      <CourseReadinessCard report={report} loading={false} onFix={onFix} />,
      renderOpts,
    )
    await user.click(screen.getByRole("button", { expanded: false }))

    expect(screen.queryByRole("button", { name: /fix/i })).toBeNull()
  })

  it("does NOT render a Fix button when the check has no action even if failing", async () => {
    const user = userEvent.setup()
    const onFix = vi.fn()
    const report = makeReport({
      checks: [
        makeCheck({
          id: "no-action",
          severity: "critical",
          passed: false,
          action: null,
          message_key: "courseReadiness.checks.hasDescription",
        }),
      ],
    })
    render(
      <CourseReadinessCard report={report} loading={false} onFix={onFix} />,
      renderOpts,
    )
    await user.click(screen.getByRole("button", { expanded: false }))

    expect(screen.queryByRole("button", { name: /fix/i })).toBeNull()
  })

  it("interpolates the subject title into the check message", async () => {
    const user = userEvent.setup()
    const report = makeReport({
      checks: [
        makeCheck({
          id: "with-subject",
          severity: "critical",
          passed: false,
          subject: { type: "module", id: "m-1", title: "Genesis Overview" },
          message_key: "courseReadiness.checks.moduleHasChapters",
        }),
      ],
    })
    render(<CourseReadinessCard report={report} loading={false} />, renderOpts)
    await user.click(screen.getByRole("button", { expanded: false }))

    // The "moduleHasChapters" key contains "{{title}}" which the
    // component interpolates from check.subject.title.
    expect(screen.getByText(/Genesis Overview/)).toBeInTheDocument()
  })

  it("displays the numeric score in the ring", () => {
    const report = makeReport({ score: 73, passing: 4, total: 5 })
    render(<CourseReadinessCard report={report} loading={false} />, renderOpts)
    expect(screen.getByText("73")).toBeInTheDocument()
  })
})
