import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import {
  CheckCircle,
  Clock,
  HeartHandshake,
  Loader2,
  RotateCcw,
  Undo2,
  XCircle,
} from "lucide-react"
import { isGradableChapterType } from "@/lib/chapterTypes"
import { chapterActions } from "./chapterActions"
import type { AssignmentResult, ChapterInfo, QuizResult } from "./helpers"

interface Props {
  chapterId: string
  chapterInfo?: ChapterInfo
  quiz?: QuizResult
  assignment?: AssignmentResult
  togglingChapterId: string | null
  grantingQuizId: string | null
  excusingChapterId: string | null
  onToggleComplete: (chapter: ChapterInfo) => void
  onGrantExtraAttempt: (quizId: string) => void
  onExcuse: (chapter: ChapterInfo) => void
  onUnexcuse: (chapter: ChapterInfo) => void
}

/**
 * One row inside a student's expanded "chapter breakdown" table. Each row
 * shows the chapter title, quiz status (if any), assignment status (if any),
 * and for gradable chapters a toggle / grant-extra-attempt affordance.
 */
export function ChapterBreakdownRow({
  chapterId,
  chapterInfo,
  quiz,
  assignment,
  togglingChapterId,
  grantingQuizId,
  excusingChapterId,
  onToggleComplete,
  onGrantExtraAttempt,
  onExcuse,
  onUnexcuse,
}: Props) {
  const { t } = useTranslation()
  const title =
    chapterInfo?.title ?? quiz?.chapter_title ?? assignment?.chapter_title ?? chapterId
  const gradable = chapterInfo ? isGradableChapterType(chapterInfo.chapter_type) : false
  const completed = chapterInfo?.completed ?? false
  const actions = chapterActions(chapterInfo)
  const busy = excusingChapterId === chapterInfo?.id

  return (
    <div className="flex items-center gap-4 bg-surface rounded-lg px-4 py-3 border text-sm">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="font-medium truncate">{title}</p>
        </div>
        {chapterInfo && gradable && (
          <p className="text-xs mt-0.5">
            {completed ? (
              <CompletionLabel completedBy={chapterInfo.completed_by} />
            ) : (
              <span className="text-ink-muted">
                {t("studentProgress.chapterRow.notCompleted")}
              </span>
            )}
          </p>
        )}
      </div>

      {quiz && (
        <div className="flex items-center gap-1.5 text-xs">
          {quiz.passed ? (
            <CheckCircle className="h-3.5 w-3.5 text-success" strokeWidth={1.75} />
          ) : (
            <XCircle className="h-3.5 w-3.5 text-destructive" strokeWidth={1.75} />
          )}
          <span>
            {t("studentProgress.chapterRow.quizScore", {
              score: quiz.score,
              max: quiz.max_score,
            })}
          </span>
          {quiz.quiz_id && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-1.5 text-xs text-ink-muted hover:text-ink"
              disabled={grantingQuizId === quiz.quiz_id}
              onClick={(e) => {
                e.stopPropagation()
                onGrantExtraAttempt(quiz.quiz_id!)
              }}
              title={t("studentProgress.chapterRow.extraAttemptTitle")}
            >
              {grantingQuizId === quiz.quiz_id ? (
                <Loader2 className="h-3 w-3 animate-spin" strokeWidth={1.75} />
              ) : (
                <RotateCcw className="h-3 w-3" strokeWidth={1.75} />
              )}
            </Button>
          )}
        </div>
      )}

      {assignment && (
        <div className="flex items-center gap-1.5 text-xs">
          {assignment.status === "graded" ? (
            <CheckCircle className="h-3.5 w-3.5 text-success" strokeWidth={1.75} />
          ) : (
            <Clock className="h-3.5 w-3.5 text-warning" strokeWidth={1.75} />
          )}
          <span>
            {assignment.title}:{" "}
            {assignment.grade !== null
              ? `${assignment.grade}/${assignment.max_score}`
              : t(`assignment.statusValue.${assignment.status}`, { defaultValue: assignment.status })}
          </span>
        </div>
      )}

      {/* An excused chapter offers one action, not two: the exemption holds the
          grade and the completion together, so undoing the tick on its own is
          refused by the server. Returning the work undoes both. */}
      {chapterInfo && actions.canReturn && (
        <Button
          variant="outline"
          size="sm"
          className="shrink-0 text-xs h-7"
          disabled={busy}
          onClick={(e) => {
            e.stopPropagation()
            onUnexcuse(chapterInfo)
          }}
        >
          {busy ? (
            <Clock className="h-3 w-3 mr-1 animate-spin" strokeWidth={1.75} />
          ) : (
            <Undo2 className="h-3 w-3 mr-1" strokeWidth={1.75} />
          )}
          {t("studentProgress.chapterRow.returnWork")}
        </Button>
      )}

      {/* Offered on finished chapters too: a student who submitted while ill
          may still be waived from the mark, and the chapter simply stays as the
          student left it. */}
      {chapterInfo && actions.canExcuse && (
        <Button
          variant="ghost"
          size="sm"
          className="shrink-0 text-xs h-7 text-ink-muted hover:text-ink"
          disabled={busy}
          onClick={(e) => {
            e.stopPropagation()
            onExcuse(chapterInfo)
          }}
          title={t("studentProgress.chapterRow.excuseTitle")}
        >
          {busy ? (
            <Clock className="h-3 w-3 mr-1 animate-spin" strokeWidth={1.75} />
          ) : (
            <HeartHandshake className="h-3 w-3 mr-1" strokeWidth={1.75} />
          )}
          {t("studentProgress.chapterRow.excuse")}
        </Button>
      )}

      {chapterInfo && actions.canToggleCompletion && (
        <Button
          variant={completed ? "outline" : "default"}
          size="sm"
          className="shrink-0 text-xs h-7"
          disabled={togglingChapterId === chapterInfo.id}
          onClick={(e) => {
            e.stopPropagation()
            onToggleComplete(chapterInfo)
          }}
        >
          {togglingChapterId === chapterInfo.id ? (
            <Clock className="h-3 w-3 mr-1 animate-spin" strokeWidth={1.75} />
          ) : completed ? (
            <XCircle className="h-3 w-3 mr-1" strokeWidth={1.75} />
          ) : (
            <CheckCircle className="h-3 w-3 mr-1" strokeWidth={1.75} />
          )}
          {completed
            ? t("studentProgress.chapterRow.undo")
            : t("studentProgress.chapterRow.complete")}
        </Button>
      )}
    </div>
  )
}

function CompletionLabel({
  completedBy,
}: {
  completedBy: ChapterInfo["completed_by"]
}) {
  const { t } = useTranslation()
  if (completedBy === "excused") {
    // Not "completed" in any sense the student would recognise. The tick is
    // the same green as work they actually did, so the label is the only place
    // the difference survives — and a certificate gets signed on it.
    return <span className="text-info">{t("studentProgress.chapterRow.excused")}</span>
  }
  if (completedBy === "teacher") {
    return <span className="text-info">{t("studentProgress.chapterRow.completedByTeacher")}</span>
  }
  if (completedBy === "quiz") {
    return <span className="text-success">{t("studentProgress.chapterRow.completedByQuiz")}</span>
  }
  return <span className="text-success">{t("studentProgress.chapterRow.completedBySubmission")}</span>
}
