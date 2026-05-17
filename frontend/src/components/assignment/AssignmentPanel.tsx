import { useState, useEffect, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { coursesService } from "@/services/courses"
import { getErrorDetail } from "@/lib/errorDetail"
import { toast } from "@/lib/toast"
import type { Assignment, AssignmentSubmission } from "@/types"

// Per-chapter request dedup. A reading chapter with N assignment blocks
// mounts N AssignmentPanel instances simultaneously, each one
// requesting the same `/api/v1/chapters/{id}/assignments` list. Without
// this map every block fires its own identical network call. The entry
// is dropped once the promise settles so subsequent mounts refetch
// fresh data.
const inflightChapterAssignments = new Map<string, Promise<Assignment[]>>()

function fetchChapterAssignmentsDeduped(chapterId: string): Promise<Assignment[]> {
  const existing = inflightChapterAssignments.get(chapterId)
  if (existing) return existing
  const promise = coursesService.getChapterAssignments(chapterId).finally(() => {
    if (inflightChapterAssignments.get(chapterId) === promise) {
      inflightChapterAssignments.delete(chapterId)
    }
  })
  inflightChapterAssignments.set(chapterId, promise)
  return promise
}
import PageSpinner from "@/components/ui/PageSpinner"
import { formatDate } from "@/i18n/format"
import {
  FileText,
  Calendar,
  Star,
  Send,
  CheckCircle,
  Clock,
  RotateCcw,
  Loader2,
  MessageSquare,
  Link as LinkIcon,
} from "lucide-react"

interface AssignmentPanelProps {
  chapterId: string
  /** Filter down to a single assignment when rendered from a ChapterBlock. */
  assignmentId?: string
  onSubmitted?: () => void
  /** Fires once after fetch with the number of assignments visible in this panel. */
  onCountLoaded?: (count: number) => void
}

export default function AssignmentPanel({ chapterId, assignmentId, onSubmitted, onCountLoaded }: AssignmentPanelProps) {
  const { t } = useTranslation()
  const [assignments, setAssignments] = useState<Assignment[]>([])
  const [submissionsMap, setSubmissionsMap] = useState<Record<string, AssignmentSubmission | null>>({})
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState(false)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setFetchError(false)
      try {
        const all = await fetchChapterAssignmentsDeduped(chapterId)
        if (cancelled) return
        const data = assignmentId ? all.filter((a) => a.id === assignmentId) : all
        setAssignments(data)
        onCountLoaded?.(data.length)

        if (data.length > 0) {
          const subResults = await Promise.all(
            data.map((a) => coursesService.getMySubmissions(a.id).catch(() => [] as AssignmentSubmission[]))
          )
          if (cancelled) return
          const map: Record<string, AssignmentSubmission | null> = {}
          data.forEach((a, i) => {
            const subs = subResults[i] ?? []
            map[a.id] = subs.length > 0 ? (subs[0] ?? null) : null
          })
          setSubmissionsMap(map)
        }
      } catch {
        if (!cancelled) setFetchError(true)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
    // Callbacks (onSubmitted, onCountLoaded) are outputs of this effect, not
    // inputs: refetching when the parent renders a new handler reference
    // would cause spurious reloads on every chapter-level state change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapterId, assignmentId])

  if (loading) {
    return <PageSpinner variant="section" />
  }
  if (fetchError) return (
    <p className="text-sm text-destructive py-4 text-center">{t("assignment.loadFailed")}</p>
  )
  if (assignments.length === 0) return null

  return (
    <div className="space-y-4 mt-6">
      {assignments.map((assignment) => (
        <SingleAssignment
          key={assignment.id}
          assignment={assignment}
          initialSubmission={submissionsMap[assignment.id] ?? null}
          onSubmitted={onSubmitted}
        />
      ))}
    </div>
  )
}

function SingleAssignment({ assignment, initialSubmission, onSubmitted }: { assignment: Assignment; initialSubmission: AssignmentSubmission | null; onSubmitted?: () => void }) {
  const { t } = useTranslation()
  const [submission, setSubmission] = useState<AssignmentSubmission | null>(initialSubmission)
  const [content, setContent] = useState("")
  const [fileUrl, setFileUrl] = useState("")
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    setSubmission(initialSubmission)
  }, [initialSubmission])

  const handleSubmit = async () => {
    if (!content.trim() && !fileUrl.trim()) return
    setSubmitting(true)
    try {
      const sub = await coursesService.submitAssignment(assignment.id, {
        content: content.trim() || undefined,
        file_url: fileUrl.trim() || undefined,
      })
      setSubmission(sub)
      setContent("")
      setFileUrl("")
      onSubmitted?.()
    } catch (error: unknown) {
      const detail = getErrorDetail(error)
      toast({ title: detail || t("toast.assignmentSubmitFailed"), variant: "destructive" })
    } finally {
      setSubmitting(false)
    }
  }

  const canResubmit = submission?.status === "returned"
  const showForm = !submission || canResubmit

  const isOverdue = assignment.due_date && new Date(assignment.due_date) < new Date()

  const statusConfig: Record<string, { icon: React.ReactNode; label: string; color: string }> = useMemo(
    () => ({
      submitted: {
        icon: <Clock className="h-4 w-4" strokeWidth={1.75} />,
        label: t("assignment.statusSubmitted"),
        color: "border-info/30 bg-info/10 text-info",
      },
      graded: {
        icon: <CheckCircle className="h-4 w-4" strokeWidth={1.75} />,
        label: t("assignment.statusGraded"),
        color: "border-success/30 bg-success/10 text-success",
      },
      returned: {
        icon: <RotateCcw className="h-4 w-4" strokeWidth={1.75} />,
        label: t("assignment.statusReturned"),
        color: "border-warning/30 bg-warning/10 text-warning",
      },
    }),
    [t],
  )

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="border-b border-border px-5 py-5">
        <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
          <FileText className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          {t("assignment.eyebrow")}
        </p>
        <h3 className="font-serif text-lg font-semibold tracking-tight text-wrap-safe">
          {assignment.title}
        </h3>
        {assignment.description && (
          <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground text-wrap-safe whitespace-pre-line">
            {assignment.description}
          </p>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span className="flex items-center gap-1 tabular-nums">
            <Star className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            {t("assignment.maxPoints", { max: assignment.max_score })}
          </span>
          {assignment.due_date && (
            <>
              <span aria-hidden className="text-muted-foreground/40">·</span>
              <span className={`flex items-center gap-1 tabular-nums ${isOverdue ? "font-medium text-destructive" : ""}`}>
                <Calendar className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                {t("assignment.due")}{" "}
                {formatDate(assignment.due_date)}
                {isOverdue && (
                  <span className="ml-1 rounded bg-destructive/10 px-1.5 py-0.5 text-xs font-medium text-destructive">
                    {t("assignment.overdue")}
                  </span>
                )}
              </span>
            </>
          )}
        </div>
      </div>

      <div className="p-5">
        {submission && (
          <div className="mb-5 space-y-3">
            <div className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm ${statusConfig[submission.status]?.color ?? ""}`}>
              {statusConfig[submission.status]?.icon}
              <span className="font-medium">{statusConfig[submission.status]?.label}</span>
            </div>

            {submission.status === "graded" && submission.grade !== null && (
              <div className="rounded-md border border-success/30 bg-success/5 px-4 py-3">
                <p className="mb-1 text-xs font-medium uppercase tracking-[0.18em] text-success">
                  {t("assignment.gradeEyebrow")}
                </p>
                <p className="font-serif text-2xl font-semibold tabular-nums tracking-tight text-success">
                  {submission.grade}
                  <span className="text-success/60"> / {assignment.max_score}</span>
                </p>
              </div>
            )}

            {submission.feedback && (
              <div className="rounded-md border border-border bg-muted/20 p-4">
                <p className="mb-1.5 flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                  <MessageSquare className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                  {t("assignment.instructorFeedback")}
                </p>
                <p className="text-sm leading-relaxed text-wrap-safe whitespace-pre-wrap">{submission.feedback}</p>
              </div>
            )}

            {submission.content && (
              <div className="rounded-md border border-border bg-muted/20 p-4">
                <p className="mb-1.5 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                  {t("assignment.yourSubmission")}
                </p>
                <p className="text-sm leading-relaxed text-wrap-safe whitespace-pre-wrap">{submission.content}</p>
              </div>
            )}
          </div>
        )}

        {showForm && (
          <div className="space-y-4">
            {canResubmit && (
              <div className="rounded-md border border-warning/30 border-l-stripe border-l-warning bg-warning/10 px-3 py-2 text-xs font-medium text-warning">
                {t("assignment.returnedHint")}
              </div>
            )}
            <div className="space-y-1.5">
              <Label className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                {t("assignment.yourResponse")}
              </Label>
              <Textarea
                fieldSize="default"
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder={t("assignment.responsePlaceholder")}
                className="min-h-[160px] leading-relaxed"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                <LinkIcon className="h-3 w-3" strokeWidth={1.75} aria-hidden />
                {t("assignment.fileLinkOptional")}
              </Label>
              <Input
                value={fileUrl}
                onChange={(e) => setFileUrl(e.target.value)}
                placeholder={t("assignment.fileLinkPlaceholder")}
                fieldSize="sm"
                className="text-sm"
              />
            </div>
            <Button
              onClick={handleSubmit}
              disabled={submitting || (!content.trim() && !fileUrl.trim())}
            >
              {submitting ? (
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />
              ) : (
                <Send className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
              )}
              {submitting ? t("assignment.submitting") : canResubmit ? t("assignment.resubmit") : t("assignment.submit")}
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
