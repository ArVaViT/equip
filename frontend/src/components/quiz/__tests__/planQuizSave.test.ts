/**
 * Saving a quiz used to mean: create a new one, delete the old one — and
 * ``quiz_attempts.quiz_id`` cascades. These pin the plan the editor makes
 * instead: what it sends to the in-place routes, that it sends only what
 * changed, and that adding or removing a question or an option is
 * recognised as the one shape those routes cannot reach.
 */

import { describe, expect, it } from "vitest"

import type { Quiz } from "@/types"
import { isEmptyPlan, planInPlaceSave, type DraftSnapshot } from "../editor/planQuizSave"
import type { DraftQuestion } from "../editor/types"

function savedQuiz(): Quiz {
  return {
    id: "quiz-1",
    chapter_id: "chap-1",
    title: "Бытие 1",
    description: null,
    quiz_type: "quiz",
    max_attempts: null,
    passing_score: 70,
    created_at: "2026-09-01T00:00:00Z",
    questions: [
      {
        id: "q1",
        quiz_id: "quiz-1",
        question_text: "Сколько дней творения?",
        question_type: "multiple_choice",
        order_index: 0,
        points: 1,
        min_words: null,
        options: [
          { id: "o1", question_id: "q1", option_text: "Шесть", is_correct: true, order_index: 0 },
          { id: "o2", question_id: "q1", option_text: "Семь", is_correct: false, order_index: 1 },
        ],
      },
      {
        id: "q2",
        quiz_id: "quiz-1",
        question_text: "Опишите день седьмой.",
        question_type: "essay",
        order_index: 1,
        points: 5,
        min_words: 100,
        options: [],
      },
    ],
  }
}

/** The draft the editor holds right after loading ``savedQuiz()``. */
function draftOf(quiz: Quiz): DraftSnapshot {
  return {
    title: quiz.title,
    description: quiz.description,
    passingScore: quiz.passing_score,
    maxAttempts: quiz.max_attempts,
    questions: quiz.questions.map(
      (q): DraftQuestion => ({
        id: q.id,
        question_text: q.question_text,
        question_type: q.question_type,
        order_index: q.order_index,
        points: q.points,
        min_words: q.min_words ?? null,
        options: q.options.map((o) => ({
          id: o.id,
          option_text: o.option_text,
          is_correct: Boolean(o.is_correct),
          order_index: o.order_index,
        })),
      }),
    ),
  }
}

describe("the plan for saving a quiz in place", () => {
  it("sends nothing when nothing changed", () => {
    const quiz = savedQuiz()
    const plan = planInPlaceSave(quiz, draftOf(quiz))
    expect(plan).not.toBeNull()
    expect(isEmptyPlan(plan!)).toBe(true)
  })

  it("a typo fix is one PATCH with one field", () => {
    const quiz = savedQuiz()
    const draft = draftOf(quiz)
    draft.questions[0]!.question_text = "Сколько было дней творения?"

    expect(planInPlaceSave(quiz, draft)).toEqual({
      quiz: null,
      questions: [{ id: "q1", patch: { question_text: "Сколько было дней творения?" } }],
      options: [],
    })
  })

  it("moving the right answer is two option PATCHes — one on, one off", () => {
    const quiz = savedQuiz()
    const draft = draftOf(quiz)
    draft.questions[0]!.options[0]!.is_correct = false
    draft.questions[0]!.options[1]!.is_correct = true

    expect(planInPlaceSave(quiz, draft)!.options).toEqual([
      { id: "o1", patch: { is_correct: false } },
      { id: "o2", patch: { is_correct: true } },
    ])
  })

  it("the fields above the questions go to the quiz itself", () => {
    const quiz = savedQuiz()
    const draft = { ...draftOf(quiz), title: "Бытие 1–2", passingScore: 80, description: "Проверка главы" }

    expect(planInPlaceSave(quiz, draft)!.quiz).toEqual({
      title: "Бытие 1–2",
      description: "Проверка главы",
      passing_score: 80,
    })
  })

  it("reordering questions patches their positions", () => {
    const quiz = savedQuiz()
    const draft = draftOf(quiz)
    draft.questions[0]!.order_index = 1
    draft.questions[1]!.order_index = 0

    expect(planInPlaceSave(quiz, draft)!.questions).toEqual([
      { id: "q1", patch: { order_index: 1 } },
      { id: "q2", patch: { order_index: 0 } },
    ])
  })

  it("treats an absent min_words and a null one as the same thing", () => {
    const quiz = savedQuiz()
    const draft = draftOf(quiz)
    draft.questions[1]!.min_words = null
    expect(planInPlaceSave(quiz, draft)!.questions).toEqual([{ id: "q2", patch: { min_words: null } }])
  })

  it("a new question is a rebuild", () => {
    const quiz = savedQuiz()
    const draft = draftOf(quiz)
    draft.questions.push({
      id: "draft-3",
      question_text: "Новый",
      question_type: "short_answer",
      order_index: 2,
      points: 1,
      min_words: null,
      options: [],
    })
    expect(planInPlaceSave(quiz, draft)).toBeNull()
  })

  it("a removed question is a rebuild", () => {
    const quiz = savedQuiz()
    const draft = draftOf(quiz)
    draft.questions.pop()
    expect(planInPlaceSave(quiz, draft)).toBeNull()
  })

  it("an added or removed option is a rebuild — a deleted option blanks a student's answer", () => {
    const quiz = savedQuiz()
    const added = draftOf(quiz)
    added.questions[0]!.options.push({ id: "draft-9", option_text: "Восемь", is_correct: false, order_index: 2 })
    expect(planInPlaceSave(quiz, added)).toBeNull()

    const removed = draftOf(quiz)
    removed.questions[0]!.options.pop()
    expect(planInPlaceSave(quiz, removed)).toBeNull()
  })

  it("a type change that keeps the option list is a PATCH the server may still refuse", () => {
    const quiz = savedQuiz()
    const draft = draftOf(quiz)
    draft.questions[1]!.question_type = "short_answer"
    draft.questions[1]!.min_words = null
    expect(planInPlaceSave(quiz, draft)!.questions).toEqual([
      { id: "q2", patch: { question_type: "short_answer", min_words: null } },
    ])
  })
})
