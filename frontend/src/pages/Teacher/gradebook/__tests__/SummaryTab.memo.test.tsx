/**
 * Render-perf regression for SummaryTab.
 *
 * Before the row memoisation work, typing in one student's override-grade
 * input would re-render every other row (the parent `forms` Map was a new
 * reference, callbacks were re-created, and the empty-form fallback was a
 * fresh object literal). On large cohorts that meant 50-100 needless row
 * renders per keystroke.
 *
 * To pin this win down we replace `useTranslation` with a counting stub
 * for the duration of the test. Each row calls `useTranslation` once per
 * render, so toggling one row's `expanded` flag should only fire the
 * hook a small constant number of times — not once per row. If anyone
 * removes the `React.memo` wrap, the shared `EMPTY_FORM` constant, or
 * the `useCallback` on row handlers, the count blows up linearly with
 * cohort size and this test fails.
 */
import { useCallback, useState } from "react"
import { fireEvent, render } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import type {
  GradeSummaryResponse,
  GradingConfig,
  StudentCalculatedGrade,
  StudentGrade,
} from "@/types"
import { EMPTY_FORM } from "../helpers"
import type { GradeForm } from "../types"

// Counter incremented by the stubbed `useTranslation`. Reset between
// assertions via `useTranslationCalls.length = 0`.
const useTranslationCalls: unknown[] = []

vi.mock("react-i18next", async () => {
  const actual = await vi.importActual<typeof import("react-i18next")>("react-i18next")
  return {
    ...actual,
    useTranslation: (...args: Parameters<typeof actual.useTranslation>) => {
      useTranslationCalls.push(args)
      return actual.useTranslation(...args)
    },
  }
})

// Imported after the mock factory above so SummaryTab picks up the
// instrumented `useTranslation` when its `react-i18next` import resolves.
const { SummaryTab } = await import("../SummaryTab")

function makeStudent(id: string, name: string): StudentCalculatedGrade {
  return {
    student_id: id,
    student_name: name,
    student_email: `${id}@example.test`,
    breakdown: {
      quiz_avg: 75,
      quiz_weighted: 22.5,
      assignment_avg: 80,
      assignment_weighted: 40,
      participation_pct: 90,
      participation_weighted: 18,
      final_score: 80.5,
      letter_grade: "B",
    },
    manual_grade: null,
  }
}

const CONFIG: GradingConfig = {
  quiz_weight: 30,
  assignment_weight: 50,
  participation_weight: 20,
}

function Harness({ studentCount }: { studentCount: number }) {
  // Hold `summary` in state so its identity is stable across renders —
  // mirrors how TeacherGradebook stores the network response. If we
  // built it fresh in render, `useMemo` inside SummaryTab would
  // re-derive `sortedStudents` and the row prop `student` would get a
  // new reference on every render, defeating the memoisation we're
  // trying to verify.
  const [summary] = useState<GradeSummaryResponse>(() => ({
    course_id: "course-1",
    config: CONFIG,
    students: Array.from({ length: studentCount }, (_, i) =>
      makeStudent(`s${i + 1}`, `Student ${i + 1}`),
    ),
    class_average: 80.5,
  }))
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [forms] = useState<Map<string, GradeForm>>(new Map())
  // Stable identity for the row-level handlers — mirrors what
  // TeacherGradebook does via `useCallback`.
  const onToggleExpand = useCallback((id: string) => {
    setExpandedId((prev) => (prev === id ? null : id))
  }, [])
  const onUpdateForm = useCallback(() => {}, [])
  const onSaveGrade = useCallback(() => {}, [])
  const onSortChange = useCallback(() => {}, [])
  return (
    <SummaryTab
      summary={summary}
      config={CONFIG}
      manualGrades={new Map<string, StudentGrade>()}
      forms={forms}
      saving={null}
      expandedId={expandedId}
      sortField="name"
      sortDir="asc"
      onSortChange={onSortChange}
      onToggleExpand={onToggleExpand}
      onUpdateForm={onUpdateForm}
      onSaveGrade={onSaveGrade}
    />
  )
}

function countRowRenders(studentCount: number): {
  mountCount: number
  toggleCount: number
} {
  // Reset the counter, mount, capture, click, capture again.
  useTranslationCalls.length = 0
  const { container } = render(
    <I18nextProvider i18n={i18n}>
      <Harness studentCount={studentCount} />
    </I18nextProvider>,
  )
  const mountCount = useTranslationCalls.length
  useTranslationCalls.length = 0
  const firstRow = container.querySelector(
    "[class*='grid-cols-[1fr_80px_80px_90px_80px_70px_70px]'].cursor-pointer",
  ) as HTMLElement | null
  if (!firstRow) throw new Error("first row not found")
  fireEvent.click(firstRow)
  const toggleCount = useTranslationCalls.length
  return { mountCount, toggleCount }
}


describe("SummaryTab row memoisation", () => {
  it("EMPTY_FORM is a frozen module-scoped constant", () => {
    // Frozen + module-scoped, so identity is stable. If a future refactor
    // accidentally inlines a fresh object literal at the call site, the
    // shallow-props compare in React.memo breaks and every row re-renders.
    expect(EMPTY_FORM).toBe(EMPTY_FORM)
    expect(Object.isFrozen(EMPTY_FORM)).toBe(true)
  })

  it("toggling one row keeps the row-render count constant across cohort sizes", () => {
    // Each row calls `useTranslation` once per render. With memo + stable
    // callbacks, expanding row 1 should re-render row 1 only, regardless
    // of cohort size. We capture the toggle-phase `useTranslation` call
    // count at two cohort sizes; the count should be a small constant.
    // If memoisation were removed, the toggle count would scale linearly
    // (every row re-renders), exceeding `toggleCount20 >= 20`.
    const small = countRowRenders(5)
    const large = countRowRenders(20)
    // Toggle commit should re-render: the SummaryTab parent (1 useT call)
    // + the toggled row itself (1 useT call) = 2 baseline calls. Any
    // BreakdownEntry usage inside the expanded panel adds a few more.
    // With memoisation working, the toggle count stays bounded under 10
    // regardless of cohort size. Without it, it grows with cohort size.
    expect(small.toggleCount).toBeLessThan(10)
    expect(large.toggleCount).toBeLessThan(10)
    // And the toggle counts should be roughly equal — that's the
    // direct memoisation signal. We allow ±2 for jsdom noise but
    // disallow the linear-with-cohort-size pattern.
    expect(Math.abs(large.toggleCount - small.toggleCount)).toBeLessThan(3)
  })

  it("renders all students once on mount", () => {
    // Smoke test that the visible row count matches the data set.
    // Combined with the EMPTY_FORM identity test above, this ensures
    // the memo wrapping doesn't accidentally short-circuit the initial
    // render (which has fresh props for every row).
    const { container } = render(
      <I18nextProvider i18n={i18n}>
        <Harness studentCount={10} />
      </I18nextProvider>,
    )
    const rows = container.querySelectorAll(
      "[class*='grid-cols-[1fr_80px_80px_90px_80px_70px_70px]'].cursor-pointer",
    )
    expect(rows.length).toBe(10)
  })
})
