import { useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import { Textarea } from "@/components/ui/textarea"
import { useLocalDraft } from "@/hooks/useLocalDraft"
import type { QuizQuestion } from "@/types"
import { EssayAnswer } from "./EssayAnswer"

interface Props {
  question: QuizQuestion
  value: string
  /** `null` when nobody is signed in to scope a draft to — nothing is kept. */
  draftKey: string | null
  onChange: (text: string) => void
  /**
   * Hands the parent this question's `clear`, and takes it back on unmount.
   * The quiz taker calls every one of them the moment an attempt is accepted:
   * the hook flushes unsent text to storage on its way out, so a draft that is
   * not cleared *before* the results screen replaces the prompts comes back
   * on the next attempt as if the student had never submitted.
   */
  onDraftClearer?: (questionId: string, clear: (() => void) | null) => void
}

/**
 * A short answer or essay inside a quiz, with the same floor the assignment
 * panel has: what is typed survives a reload.
 *
 * The answers lived only in the quiz taker's state. A phone dropping the tab,
 * a reload, a tap on the wrong lesson — and an exam essay was gone, with the
 * attempt sometimes spent on it. `useLocalDraft` already knew how to keep an
 * assignment's text; this is the same hook, one per open question, keyed to
 * the student, the quiz and the question (2026-10-03).
 */
export function OpenAnswer({ question, value, draftKey, onChange, onDraftClearer }: Props) {
  const { t } = useTranslation()
  const { restored, savedAt, clear } = useLocalDraft(draftKey, value)

  useEffect(() => {
    onDraftClearer?.(question.id, clear)
    return () => onDraftClearer?.(question.id, null)
  }, [question.id, clear, onDraftClearer])

  // Applied once. `onChange` is a fresh closure on every parent render, and
  // re-applying the draft each time would put the restored text back over
  // whatever the student typed since.
  const applied = useRef(false)
  useEffect(() => {
    if (restored === null || applied.current) return
    applied.current = true
    onChange(restored)
  }, [restored, onChange])

  return (
    <>
      {question.question_type === "essay" ? (
        <EssayAnswer value={value} minWords={question.min_words} onChange={onChange} />
      ) : (
        <div className="ml-9">
          <Textarea
            fieldSize="default"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={t("quiz.typeAnswerPlaceholder")}
          />
        </div>
      )}
      {/* Quiet, and only once there is something to say — the assignment
          panel's rule. */}
      {(restored !== null || savedAt !== null) && (
        <p className="ml-9 text-xs text-ink-muted" role="status">
          {restored ? t("quiz.draftRestored") : t("quiz.draftSaved")}
        </p>
      )}
    </>
  )
}
