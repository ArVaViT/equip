import { useState, useEffect, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { coursesService } from "@/services/courses"
import { getErrorDetail } from "@/lib/errorDetail"
import { rubricsService } from "@/services/rubrics"
import { useAuth } from "@/context/useAuth"
import { useLocalDraft } from "@/hooks/useLocalDraft"
import { assignmentDraftKey } from "@/lib/storageKeys"
import { SubmissionDeclaration, type DeclarationState } from "./SubmissionDeclaration"
import { declarationStatement } from "./declarationStatement"
import { RubricGrid } from "@/components/rubric/RubricGrid"
import { toast } from "@/lib/toast"
import type { AiPolicy, Assignment, AssignmentSubmission, SubmissionRubric } from "@/types"
import PageSpinner from "@/components/ui/PageSpinner"
import { formatDate } from "@/i18n/format"
import { orNotTranslated } from "@/lib/untranslated"
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
  AlertTriangle,
} from "lucide-react"

/**
 * "We could not find out", as distinct from "there is nothing".
 *
 * A string rather than a Symbol so it survives the trip through a mocked
 * service in a test without ceremony, and so a failure is legible in a React
 * DevTools state dump instead of showing as `Symbol()`.
 */
const UNKNOWN = "unknown" as const

interface AssignmentPanelProps {
  /** The course's AI policy, passed down so the declaration says the right
   *  thing on the screen where the work is actually handed in. */
  aiPolicy?: AiPolicy
  chapterId: string
  /** Filter down to a single assignment when rendered from a ChapterBlock. */
  assignmentId?: string
  onSubmitted?: () => void
  /** Fires once after fetch with the number of assignments visible in this panel. */
  onCountLoaded?: (count: number) => void
}

export default function AssignmentPanel({ chapterId, assignmentId, onSubmitted, onCountLoaded, aiPolicy }: AssignmentPanelProps) {
  const { t } = useTranslation()
  const [assignments, setAssignments] = useState<Assignment[]>([])
  // Three values, not two. `null` means the student has not handed anything in;
  // `UNKNOWN` means the request to find out failed. Collapsing the second into
  // the first is what re-showed the submit form to a student who had already
  // submitted — see the note on the fetch below.
  const [submissionsMap, setSubmissionsMap] =
    useState<Record<string, AssignmentSubmission | null | typeof UNKNOWN>>({})
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState(false)

  // `reloadKey` rather than exposing `load`: the effect owns the cancellation
  // flag, and a retry that re-enters `load` directly would race the mount call
  // it is retrying. Bumping the key tears the old run down first.
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setFetchError(false)
      try {
        // ``services/api.ts`` already dedups concurrent identical GETs
        // via its ``dedupeKey`` machinery — a chapter that mounts N
        // AssignmentPanel instances simultaneously will see N callers
        // share one in-flight request automatically. The previous
        // per-module ``inflightChapterAssignments`` Map duplicated
        // that behaviour and would have diverged if the api-layer
        // policy ever changed.
        // When the panel is scoped to a single assignment we already know
        // the submissions endpoint we'll need — kick it off in parallel
        // with the assignment list instead of waterfalling behind it.
        // A failed fetch resolves to UNKNOWN, not to an empty list. The old
        // `.catch(() => [])` was the difference between "you have not handed
        // this in" and "we could not reach the server", and on a flaky
        // connection the student was shown the first — an empty form over
        // work they had already submitted, with no hint that anything was
        // wrong. Some of them would have typed it again.
        //
        // The catch stays attached at creation so a failed prefetch can never
        // surface as an unhandled rejection.
        const prefetchedSubmissions = assignmentId
          ? coursesService.getMySubmissions(assignmentId).catch(() => UNKNOWN)
          : null
        const all = await coursesService.getChapterAssignments(chapterId)
        if (cancelled) return
        const data = assignmentId ? all.filter((a) => a.id === assignmentId) : all
        setAssignments(data)
        onCountLoaded?.(data.length)

        if (data.length > 0) {
          const subResults = await Promise.all(
            data.map((a) =>
              prefetchedSubmissions && a.id === assignmentId
                ? prefetchedSubmissions
                : coursesService.getMySubmissions(a.id).catch(() => UNKNOWN)
            )
          )
          if (cancelled) return
          const map: Record<string, AssignmentSubmission | null | typeof UNKNOWN> = {}
          data.forEach((a, i) => {
            const subs = subResults[i]
            if (subs === UNKNOWN || subs === undefined) {
              map[a.id] = UNKNOWN
              return
            }
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
  }, [chapterId, assignmentId, reloadKey])

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
          onRetry={() => setReloadKey((k) => k + 1)}
          onSubmitted={onSubmitted}
          aiPolicy={aiPolicy}
        />
      ))}
    </div>
  )
}

function SingleAssignment({
  assignment,
  initialSubmission,
  onSubmitted,
  onRetry,
  aiPolicy,
}: {
  assignment: Assignment
  initialSubmission: AssignmentSubmission | null | typeof UNKNOWN
  onSubmitted?: () => void
  /** Re-runs the panel's fetch. Only reachable from the unknown state. */
  onRetry?: () => void
  /** The course's rule about what may be used. Defaults to disclosure, which
   *  is what the server assumes when a course predates the column. */
  aiPolicy?: AiPolicy
}) {
  const { t } = useTranslation()
  const unknown = initialSubmission === UNKNOWN
  const [submission, setSubmission] = useState<AssignmentSubmission | null>(
    unknown ? null : initialSubmission,
  )
  const [content, setContent] = useState("")
  const { user } = useAuth()
  // Nine hundred words used to live only in this component's state, so a
  // reload — or a phone dropping the tab out of memory — took the lot.
  const { restored, savedAt, clear: clearDraft } = useLocalDraft(
    user ? assignmentDraftKey(user.id, assignment.id) : null,
    content,
  )
  useEffect(() => {
    if (restored) setContent(restored)
  }, [restored])
  const [fileUrl, setFileUrl] = useState("")
  const [submitting, setSubmitting] = useState(false)
  // The same grid the teacher marked on. Not a summary of it: a student's
  // «summary of your rubric» drifts from the thing the mark came from, and the
  // drift is exactly where «почему у меня 70» stops having an answer.
  const [rubric, setRubric] = useState<SubmissionRubric | null>(null)
  const [declaration, setDeclaration] = useState<DeclarationState>({
    confirmed: false,
    usedAi: false,
    note: "",
  })

  useEffect(() => {
    setSubmission(initialSubmission === UNKNOWN ? null : initialSubmission)
  }, [initialSubmission])

  useEffect(() => {
    if (!submission) {
      setRubric(null)
      return
    }
    let cancelled = false
    rubricsService
      .forSubmission(submission.id)
      // Most assignments have no rubric today, and a failure here must not
      // take the student's own work off their screen.
      .catch(() => null)
      .then((r) => {
        if (!cancelled) setRubric(r)
      })
    return () => {
      cancelled = true
    }
  }, [submission])

  const policy = aiPolicy ?? "ai_with_disclosure"
  const declarationNeeded = policy !== "ai_open"

  const handleSubmit = async () => {
    if (!content.trim() && !fileUrl.trim()) return
    if (declarationNeeded && !declaration.confirmed) return
    setSubmitting(true)
    try {
      const sub = await coursesService.submitAssignment(assignment.id, {
        content: content.trim() || undefined,
        file_url: fileUrl.trim() || undefined,
        declaration: declarationNeeded
          ? {
              ai_use: declaration.usedAi ? "assisted" : "none",
              // The text as displayed, not a pointer to it.
              statement: declarationStatement(policy, t),
              note: declaration.usedAi ? declaration.note.trim() || undefined : undefined,
            }
          : undefined,
      })
      setSubmission(sub)
      setContent("")
      setFileUrl("")
      clearDraft()
      onSubmitted?.()
    } catch (error: unknown) {
      const detail = getErrorDetail(error)
      toast({ title: detail || t("toast.assignmentSubmitFailed"), variant: "destructive" })
    } finally {
      setSubmitting(false)
    }
  }

  const canResubmit = submission?.status === "returned"
  // Never offer the form while the answer is unknown. Handing a student an
  // empty textarea over work they may already have submitted is the one
  // outcome worth refusing outright — a second copy of an essay is a mess for
  // them and for whoever marks it.
  const showForm = !unknown && (!submission || canResubmit)

  const isOverdue = assignment.due_date && new Date(assignment.due_date) < new Date()

  const statusConfig: Record<string, { icon: React.ReactNode; label: string; color: string }> = useMemo(
    () => ({
      submitted: {
        icon: <Clock className="h-4 w-4" strokeWidth={1.75} />,
        label: t("assignment.statusSubmitted"),
        color: "border-info/30 bg-info/10 text-info-ink",
      },
      graded: {
        icon: <CheckCircle className="h-4 w-4" strokeWidth={1.75} />,
        label: t("assignment.statusGraded"),
        color: "border-success/30 bg-success/10 text-success-ink",
      },
      returned: {
        icon: <RotateCcw className="h-4 w-4" strokeWidth={1.75} />,
        label: t("assignment.statusReturned"),
        color: "border-warning/30 bg-warning/10 text-warning-ink",
      },
    }),
    [t],
  )

  return (
    <div className="rounded-lg border border-edge dark:border-transparent bg-card">
      <div className="border-b border-edge px-5 py-5">
        <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
          <FileText className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          {t("assignment.eyebrow")}
        </p>
        <h3 className="font-serif text-lg font-semibold tracking-tight text-wrap-safe">
          {orNotTranslated(t, assignment.title)}
        </h3>
        {assignment.description && (
          <p className="mt-1.5 text-sm leading-relaxed text-ink-muted text-wrap-safe whitespace-pre-line">
            {assignment.description}
          </p>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
          <span className="flex items-center gap-1 tabular-nums">
            <Star className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            {t("assignment.maxPoints", { max: assignment.max_score })}
          </span>
          {assignment.due_date && (
            <>
              <span aria-hidden className="text-ink-muted">·</span>
              <span className={`flex items-center gap-1 tabular-nums ${isOverdue ? "font-medium text-destructive" : ""}`}>
                <Calendar className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                {t("assignment.due")}{" "}
                {formatDate(assignment.due_date)}
                {isOverdue && (
                  <span className="ml-1 rounded bg-destructive/10 px-1.5 py-0.5 text-xs font-medium text-destructive-ink">
                    {t("assignment.overdue")}
                  </span>
                )}
              </span>
            </>
          )}
        </div>
      </div>

      <div className="p-5">
        {/* The honest third state. It says what is not known, why the form is
            not there, and offers the one action that can change the answer.
            Deliberately not a toast: a toast disappears, and the student is
            left looking at a screen that has silently changed meaning. */}
        {unknown && (
          <div
            role="status"
            className="mb-5 rounded-md border border-warning/30 bg-warning/10 px-4 py-3"
          >
            <p className="flex items-center gap-2 text-sm font-medium text-warning-ink">
              <AlertTriangle className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden />
              {t("assignment.statusUnknownTitle")}
            </p>
            <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">
              {t("assignment.statusUnknownHelp")}
            </p>
            {onRetry && (
              <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
                {t("assignment.statusUnknownRetry")}
              </Button>
            )}
          </div>
        )}
        {submission && (
          <div className="mb-5 space-y-3">
            <div className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm ${statusConfig[submission.status]?.color ?? ""}`}>
              {statusConfig[submission.status]?.icon}
              <span className="font-medium">{statusConfig[submission.status]?.label}</span>
            </div>

            {submission.status === "graded" && submission.grade !== null && (
              <div className="rounded-md border border-success/30 bg-success/5 px-4 py-3">
                <p className="mb-1 text-xs font-medium uppercase tracking-[0.18em] text-success-ink">
                  {t("assignment.gradeEyebrow")}
                </p>
                <p className="font-serif text-2xl font-semibold tabular-nums tracking-tight text-success-ink">
                  {submission.grade}
                  <span className="text-success-ink"> / {assignment.max_score}</span>
                </p>
              </div>
            )}

            {/* Where the number came from, in the same grid the teacher used —
                including the levels this work did not reach, which is the part
                that answers «а что нужно было сделать». */}
            {rubric?.rubric && submission.status === "graded" && (
              <div className="rounded-md border border-edge px-4 py-3">
                <p className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
                  {t("rubric.yourGrid")}
                </p>
                <RubricGrid rubric={rubric.rubric} marks={rubric.marks} />
              </div>
            )}

            {submission.feedback && (
              <div className="rounded-md bg-muted/20 p-4">
                <p className="mb-1.5 flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
                  <MessageSquare className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                  {t("assignment.instructorFeedback")}
                </p>
                <p className="text-sm leading-relaxed text-wrap-safe whitespace-pre-wrap">{submission.feedback}</p>
              </div>
            )}

            {submission.content && (
              <div className="rounded-md bg-muted/20 p-4">
                <p className="mb-1.5 text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
                  {t("assignment.yourSubmission")}
                </p>
                <p className="text-sm leading-relaxed text-wrap-safe whitespace-pre-wrap">{submission.content}</p>
              </div>
            )}
          </div>
        )}

        {showForm && (
          <div className="space-y-4">
            {/* Before the work, not after it: the reminder that was found to
                work in unproctored settings is one shown ahead of the act. */}
            <SubmissionDeclaration policy={policy} value={declaration} onChange={setDeclaration} />
            {canResubmit && (
              <div className="rounded-md border border-warning/30 border-l-stripe border-l-warning bg-warning/10 px-3 py-2 text-xs font-medium text-warning-ink">
                {t("assignment.returnedHint")}
              </div>
            )}
            <div className="space-y-1.5">
              <Label className="text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
                {t("assignment.yourResponse")}
              </Label>
              <Textarea
                fieldSize="default"
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder={t("assignment.responsePlaceholder")}
                className="min-h-[160px] leading-relaxed"
              />
              {/* Quiet, and only once there is something to say. A student who
                  has typed one word does not need reassurance; one who comes
                  back to find their essay still there needs to know why. */}
              {savedAt !== null && (
                <p className="text-xs text-ink-muted" role="status">
                  {restored ? t("assignment.draftRestored") : t("assignment.draftSaved")}
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
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
              // Never pre-ticked, and the button does nothing until it is —
              // the same rule the legal agreements follow, for the same reason.
              disabled={
                submitting ||
                (!content.trim() && !fileUrl.trim()) ||
                (declarationNeeded && !declaration.confirmed)
              }
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
