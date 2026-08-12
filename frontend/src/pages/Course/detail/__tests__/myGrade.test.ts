import { describe, expect, it } from "vitest"
import { myGradeDisplay, outstandingItems } from "../myGrade"
import type { MyCourseGrade, MyGradeItem } from "@/types"

function grade(over: Partial<MyCourseGrade> = {}): MyCourseGrade {
  return {
    course_id: "c1",
    grading_scheme: "letter",
    pass_threshold: "70.00",
    progress: 50,
    current_score: 82,
    current_symbol: "B",
    final_score: 82,
    final_symbol: "B",
    scores_differ: false,
    result_state: "graded",
    scores_withheld: false,
    zachet: null,
    official_grade: null,
    comment: null,
    certificate_blockers: [],
    items: [],
    ...over,
  }
}

function item(over: Partial<MyGradeItem> = {}): MyGradeItem {
  return {
    item_id: "i1",
    chapter_id: "ch",
    title: "Работа",
    kind: "quiz",
    status: "graded",
    score: 90,
    feedback: null,
    ...over,
  }
}

describe("myGradeDisplay", () => {
  it("shows one number when nothing is outstanding", () => {
    expect(myGradeDisplay(grade())).toEqual({
      headline: "82.0% B",
      isManual: false,
      finalText: null,
      noteKey: null,
    })
  })

  it("shows both the moment they diverge", () => {
    // The student meets «итоговая» here, weeks before it can refuse them a
    // certificate — which is the entire reason this card exists.
    const d = myGradeDisplay(
      grade({ current_score: 100, current_symbol: "A", final_score: 25, final_symbol: "F", scores_differ: true }),
    )

    expect(d.headline).toBe("100.0% A")
    expect(d.finalText).toBe("25.0% F")
  })

  it("formats exactly as the teacher's screens do", () => {
    // Same string on both sides, so a student and a teacher looking at the
    // same grade are looking at the same characters.
    expect(myGradeDisplay(grade({ current_score: 86.5, current_symbol: "B" })).headline).toBe("86.5% B")
  })

  it("prefers a hand-set grade over both computed numbers", () => {
    const d = myGradeDisplay(grade({ official_grade: "A", current_score: 41, scores_differ: true }))

    expect(d.headline).toBe("A")
    expect(d.isManual).toBe(true)
    expect(d.finalText).toBeNull()
  })

  it("shows the verdict on a completion-graded course, not a missing number", () => {
    // «Зачёт» is not an average clearing a line (D2), and withholding the
    // percentage while saying nothing in its place would leave the student
    // worse informed than before the scheme existed.
    const d = myGradeDisplay(
      grade({ scores_withheld: true, grading_scheme: "pass_fail", zachet: "zachet" }),
      (k) => k,
    )

    expect(d.headline).toBe("myGrade.zachet.zachet")
    expect(d.noteKey).toBeNull()
  })

  it("says why when a completion-graded course has no verdict yet", () => {
    const d = myGradeDisplay(grade({ scores_withheld: true, zachet: null }))

    expect(d.headline).toBeNull()
    expect(d.noteKey).toBe("myGrade.state.byCompletion")
  })

  it.each([
    ["not_graded_yet", "myGrade.state.notGradedYet"],
    ["zero_weighted", "myGrade.state.notWeighted"],
    ["not_assessed", "myGrade.state.notAssessed"],
    ["completion_pass", "myGrade.state.byCompletion"],
  ])("explains an absent number for %s", (state, note) => {
    const d = myGradeDisplay(grade({ current_score: null, final_score: null, result_state: state }))

    expect(d.headline).toBeNull()
    expect(d.noteKey).toBe(note)
  })

  it("drops the symbol on a scheme that has none", () => {
    expect(myGradeDisplay(grade({ current_symbol: null, final_symbol: null })).headline).toBe("82.0%")
  })
})

describe("outstandingItems", () => {
  it("puts the work they owe first and the excused last", () => {
    // A list sorted by what to do next, not by chapter order: the point of the
    // list is answering "what is left".
    // Ordered by whose move it is: what the student still owes comes first.
    const sorted = outstandingItems([
      item({ title: "Проверено", status: "graded" }),
      item({ title: "Освобождено", status: "excused" }),
      item({ title: "Не сдано", status: "not_submitted" }),
      item({ title: "Ждёт проверки", status: "pending_review" }),
      item({ title: "Возвращено", status: "returned" }),
    ])

    expect(sorted.map((i) => i.status)).toEqual([
      "not_submitted",
      "returned",
      "pending_review",
      "graded",
      "excused",
    ])
  })

  it("breaks ties by title so the order is stable between renders", () => {
    const sorted = outstandingItems([
      item({ title: "Б", status: "not_submitted" }),
      item({ title: "А", status: "not_submitted" }),
    ])

    expect(sorted.map((i) => i.title)).toEqual(["А", "Б"])
  })

  it("does not mutate the array it was given", () => {
    const original = [item({ title: "Проверено" }), item({ title: "Не сдано", status: "not_submitted" })]
    const before = [...original]

    outstandingItems(original)

    expect(original).toEqual(before)
  })
})

describe("a completion-graded course", () => {
  it("translates a hand-set verdict rather than printing its code", () => {
    // The override is stored as `pass` (D7). Printed raw it read «pass» beside
    // a computed «Зачёт» — the same verdict in two languages depending on who
    // decided it.
    const d = myGradeDisplay(
      grade({ scores_withheld: true, grading_scheme: "pass_fail", official_grade: "pass" }),
      (k) => k,
    )

    expect(d.headline).toBe("myGrade.zachet.zachet")
    expect(d.isManual).toBe(true)
  })

  it("leaves a symbol from a graded scheme alone", () => {
    // «A» is already the word the school uses; only pass/fail codes need it.
    expect(myGradeDisplay(grade({ official_grade: "A" }), (k) => k).headline).toBe("A")
  })
})
