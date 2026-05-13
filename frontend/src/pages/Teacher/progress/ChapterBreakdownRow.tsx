import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import {
  CheckCircle,
  Clock,
  Loader2,
  RotateCcw,
  XCircle,
} from "lucide-react"
import { isGradableChapterType } from "@/lib/chapterTypes"
import type { AssignmentResult, ChapterInfo, QuizResult } from "./helpers"

interface Props {
  chapterId: string
  chapterInfo?: ChapterInfo
  quiz?: QuizResult
  assignment?: AssignmentResult
  togglingChapterId: string | null
  grantingQuizId: string | null
  onToggleComplete: (chapter: ChapterInfo) => void
  onGrantExtraAttempt: (quizId: string) => void
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
  onToggleComplete,
  onGrantExtraAttempt,
}: Props) {
  const { t } = useTranslation()
  const title =
    chapterInfo?.title ?? quiz?.chapter_title ?? assignment?.chapter_title ?? chapterId
  const gradable = chapterInfo ? isGradableChapterType(chapterInfo.chapter_type) : false
  const completed = chapterInfo?.completed ?? false

  return (
    <div className="flex items-center gap-4 bg-background rounded-lg px-4 py-3 border text-sm">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="font-medium truncate">{title}</p>
        </div>
        {chapterInfo && gradable && (
          <p className="text-xs mt-0.5">
            {completed ? (
              <CompletionLabel completedBy={chapterInfo.completed_by} />
            ) : (
              <span className="text-muted-foreground">
                {t("studentProgress.chapterRow.notCompleted")}
              </span>
            )}
          </p>
        )}
      </div>

      {quiz && (
        <div className="flex items-center gap-1.5 text-xs">
          {quiz.passed ? (
            <CheckCircle className="h-3.5 w-3.5 text-success" />
          ) : (
            <XCircle className="h-3.5 w-3.5 text-destructive" />
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
              className="h-6 px-1.5 text-[10px] text-muted-foreground hover:text-foreground"
              disabled={grantingQuizId === quiz.quiz_id}
              onClick={(e) => {
                e.stopPropagation()
                onGrantExtraAttempt(quiz.quiz_id!)
              }}
              title={t("studentProgress.chapterRow.extraAttemptTitle")}
            >
              {grantingQuizId === quiz.quiz_id ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <RotateCcw className="h-3 w-3" />
              )}
            </Button>
          )}
        </div>
      )}

      {assignment && (
        <div className="flex items-center gap-1.5 text-xs">
          {assignment.status === "graded" ? (
            <CheckCircle className="h-3.5 w-3.5 text-success" />
          ) : (
            <Clock className="h-3.5 w-3.5 text-warning" />
          )}
          <span>
            {assignment.title}:{" "}
            {assignment.grade !== null
              ? `${assignment.grade}/${assignment.max_score}`
              : assignment.status}
          </span>
        </div>
      )}

      {chapterInfo && gradable && (
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
            <Clock className="h-3 w-3 mr-1 animate-spin" />
          ) : completed ? (
            <XCircle className="h-3 w-3 mr-1" />
          ) : (
            <CheckCircle className="h-3 w-3 mr-1" />
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
  if (completedBy === "teacher") {
    return <span className="text-info">{t("studentProgress.chapterRow.completedByTeacher")}</span>
  }
  if (completedBy === "quiz") {
    return <span className="text-success">{t("studentProgress.chapterRow.completedByQuiz")}</span>
  }
  return <span className="text-success">{t("studentProgress.chapterRow.completedBySubmission")}</span>
}
