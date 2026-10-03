/**
 * Saving a quiz used to mean: create a new one, delete the old one — and
 * ``quiz_attempts.quiz_id`` cascades. These pin the plan the editor makes
 * instead: what it sends to the in-place routes, that it sends only the
 * questions that changed — each one whole, with every option, so the
 * server never sees a question half-edited (2026-10-03) — and that adding
 * or removing a question or an option is recognised as the one shape
 * those routes cannot reach.
 */

import { describe, expect, it } from "vitest"

import type { Quiz } from "@/types"
import { adoptServerIds, isEmptyPlan, planInPlaceSave, type DraftSnapshot } from "../editor/planQuizSave"
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
    quizType: quiz.quiz_type,
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

  it("a typo fix sends that question whole, with its options, and nothing else", () => {
    const quiz = savedQuiz()
    const draft = draftOf(quiz)
    draft.questions[0]!.question_text = "Сколько было дней творения?"

    expect(planInPlaceSave(quiz, draft)).toEqual({
      quiz: null,
      questions: [
        {
          id: "q1",
          question: {
            question_text: "Сколько было дней творения?",
            question_type: "multiple_choice",
            order_index: 0,
            points: 1,
            min_words: null,
            options: [
              { id: "o1", option_text: "Шесть", is_correct: true, order_index: 0 },
              { id: "o2", option_text: "Семь", is_correct: false, order_index: 1 },
            ],
          },
        },
      ],
    })
  })

  it("moving the right answer is one request carrying both options — never a question with none", () => {
    const quiz = savedQuiz()
    const draft = draftOf(quiz)
    draft.questions[0]!.options[0]!.is_correct = false
    draft.questions[0]!.options[1]!.is_correct = true

    const plan = planInPlaceSave(quiz, draft)!
    expect(plan.questions).toHaveLength(1)
    expect(plan.questions[0]!.id).toBe("q1")
    expect(plan.questions[0]!.question.options.map((o) => [o.id, o.is_correct])).toEqual([
      ["o1", false],
      ["o2", true],
    ])
  })

  it("an option's wording sends its question whole, by the server's option ids", () => {
    const quiz = savedQuiz()
    const draft = draftOf(quiz)
    draft.questions[0]!.options[1]!.option_text = "Восемь"

    const plan = planInPlaceSave(quiz, draft)!
    expect(plan.questions.map((q) => q.id)).toEqual(["q1"])
    expect(plan.questions[0]!.question.options).toEqual([
      { id: "o1", option_text: "Шесть", is_correct: true, order_index: 0 },
      { id: "o2", option_text: "Восемь", is_correct: false, order_index: 1 },
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

  it("a lesson turned into an exam takes the quiz with it", () => {
    // The server decides from quiz_type whether a finished attempt shows the
    // right answers; left behind, an «exam» kept showing them.
    const quiz = savedQuiz()
    const draft = { ...draftOf(quiz), quizType: "exam" as const, maxAttempts: 1 }

    expect(planInPlaceSave(quiz, draft)!.quiz).toEqual({ max_attempts: 1, quiz_type: "exam" })
  })

  it("reordering questions sends both with their new positions", () => {
    const quiz = savedQuiz()
    const draft = draftOf(quiz)
    draft.questions[0]!.order_index = 1
    draft.questions[1]!.order_index = 0

    const plan = planInPlaceSave(quiz, draft)!
    expect(plan.questions.map((q) => [q.id, q.question.order_index])).toEqual([
      ["q1", 1],
      ["q2", 0],
    ])
  })

  it("treats an absent min_words and a null one as the same thing", () => {
    const quiz = savedQuiz()
    const draft = draftOf(quiz)
    draft.questions[1]!.min_words = null
    const plan = planInPlaceSave(quiz, draft)!
    expect(plan.questions.map((q) => q.id)).toEqual(["q2"])
    expect(plan.questions[0]!.question.min_words).toBeNull()
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

  it("a type change that keeps the option list is an in-place save the server may still refuse", () => {
    const quiz = savedQuiz()
    const draft = draftOf(quiz)
    draft.questions[1]!.question_type = "short_answer"
    draft.questions[1]!.min_words = null
    const plan = planInPlaceSave(quiz, draft)!
    expect(plan.questions.map((q) => [q.id, q.question.question_type, q.question.min_words])).toEqual([
      ["q2", "short_answer", null],
    ])
  })
})

describe("adoptServerIds", () => {
  const draftQ = (id: string, order: number, opts: string[]) => ({
    id,
    question_text: `Q${order}`,
    question_type: "multiple_choice" as const,
    order_index: order,
    points: 1,
    min_words: null,
    options: opts.map((o, i) => ({ id: o, option_text: o, is_correct: i === 0, order_index: i })),
  })

  it("takes the server's ids and keeps the draft's text", () => {
    const draft = [draftQ("tmp-1", 0, ["tmp-a", "tmp-b"])]
    const saved = {
      questions: [
        { id: "q-srv", order_index: 0, question_text: "", options: [
          { id: "o-srv-1", order_index: 0 }, { id: "o-srv-2", order_index: 1 },
        ] },
      ],
    } as unknown as Quiz
    const [q] = adoptServerIds(draft, saved)
    expect(q!.id).toBe("q-srv")
    expect(q!.question_text).toBe("Q0")
    expect(q!.options.map((o) => o.id)).toEqual(["o-srv-1", "o-srv-2"])
    expect(q!.options.map((o) => o.option_text)).toEqual(["tmp-a", "tmp-b"])
  })

  it("leaves the draft alone when the shapes differ", () => {
    const draft = [draftQ("tmp-1", 0, ["tmp-a", "tmp-b"])]
    const saved = { questions: [] } as unknown as Quiz
    expect(adoptServerIds(draft, saved)).toBe(draft)
  })
})
