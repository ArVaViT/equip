import { useState, useEffect, useMemo, useRef } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { coursesService } from "@/services/courses"
import { storageService } from "@/services/storage"
import { getErrorDetail } from "@/lib/errorDetail"
import { answerWasLost, newestUnseen } from "@/lib/lostResponse"
import { describeUploadError, preflightUpload } from "@/lib/uploadError"
import { acceptAttribute, maxMb, MB, SUBMISSIONS } from "@/lib/uploadLimits"
import { rubricsService } from "@/services/rubrics"
import { useAuth } from "@/context/useAuth"
import { useLocalDraft } from "@/hooks/useLocalDraft"
import { assignmentDraftKey } from "@/lib/storageKeys"
import { SubmissionDeclaration } from "./SubmissionDeclaration"
import { BLANK_DECLARATION, type DeclarationState, declarationStatement } from "./declarationStatement"
import { SubmissionFileChip } from "./SubmissionFileChip"
import { RubricGrid } from "@/components/rubric/RubricGrid"
import { ErrorState, LateBadge } from "@/components/patterns"
import { toast } from "@/lib/toast"
import { repeatsTitle } from "@/lib/repeatsTitle"
import type { AiPolicy, Assignment, AssignmentSubmission, SubmissionRubric } from "@/types"
import PageSpinner from "@/components/ui/PageSpinner"
import { formatDateTimeZoned } from "@/i18n/format"
import { formatNumber } from "@/i18n/number"
import { asPlainText } from "@/lib/plainText"
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
  Paperclip,
  X,
  AlertTriangle,
} from "lucide-react"
import { ScriptureText } from "@/components/chapter/ScriptureText"

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
  /** The course the chapter belongs to. A handed-in file is filed under
   *  `<course>/<assignment>/<student>/` in the bucket, and both the bucket's
   *  RLS and the API hold the key to that shape. */
  courseId: string
  chapterId: string
  /** Filter down to a single assignment when rendered from a ChapterBlock. */
  assignmentId?: string
  onSubmitted?: () => void
  /** Fires once after fetch with the number of assignments visible in this panel. */
  onCountLoaded?: (count: number) => void
  /** The page's own title, when the whole lesson is the assignment. The
   *  page already says «Задание» and its name; the card then drops the
   *  eyebrow, and the name too when it only repeats the page's. */
  pageTitle?: string
}

export default function AssignmentPanel({ courseId, chapterId, assignmentId, onSubmitted, onCountLoaded, aiPolicy, pageTitle }: AssignmentPanelProps) {
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
  if (fetchError) {
    return (
      <ErrorState
        className="py-6"
        title={t("assignment.loadFailed")}
        action={
          <Button size="sm" variant="outline" onClick={() => setReloadKey((k) => k + 1)}>
            {t("common.tryAgain")}
          </Button>
        }
      />
    )
  }
  if (assignments.length === 0) return null

  return (
    <div className="space-y-4 mt-6">
      {assignments.map((assignment) => (
        <SingleAssignment
          key={assignment.id}
          courseId={courseId}
          assignment={assignment}
          initialSubmission={submissionsMap[assignment.id] ?? null}
          onRetry={() => setReloadKey((k) => k + 1)}
          onSubmitted={onSubmitted}
          aiPolicy={aiPolicy}
          pageTitle={pageTitle}
        />
      ))}
    </div>
  )
}

/**
 * The file between «choose» and «hand in».
 *
 * `uploading` while the bytes travel (with how far they got), `ready` once
 * the bucket has them and the key can go in with the work, `failed` when
 * Storage or the network refused -- the chip stays so the student can see
 * which file it was and try again or remove it.
 */
type PendingFile =
  | { state: "uploading"; name: string; size: number; progress: number }
  | { state: "ready"; name: string; size: number; bucket: string; path: string }
  | { state: "failed"; name: string; size: number; message: string }

function SingleAssignment({
  courseId,
  assignment,
  initialSubmission,
  onSubmitted,
  onRetry,
  aiPolicy,
  pageTitle,
}: {
  pageTitle?: string
  courseId: string
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
  const [file, setFile] = useState<PendingFile | null>(null)
  // The link field is hidden until asked for: a student with a photo of
  // their notebook does not need to know what a URL is. It comes out on
  // «или вставить ссылку», or on its own when the file cannot go in the
  // bucket (too big, wrong kind) -- the link is the way round that.
  const [linkShown, setLinkShown] = useState(false)
  const [fileUrl, setFileUrl] = useState("")
  const [fileIssue, setFileIssue] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const [submitting, setSubmitting] = useState(false)
  // The same grid the teacher marked on. Not a summary of it: a student's
  // «summary of your rubric» drifts from the thing the mark came from, and the
  // drift is exactly where «почему у меня 70» stops having an answer.
  const [rubric, setRubric] = useState<SubmissionRubric | null>(null)
  const [declaration, setDeclaration] = useState<DeclarationState>(BLANK_DECLARATION)

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

  const chooseFile = async (chosen: File | undefined) => {
    // The same input can be used again for the same file: clear it.
    if (fileInput.current) fileInput.current.value = ""
    if (!chosen || !user) return
    setFileIssue(null)
    const issue = preflightUpload(chosen, SUBMISSIONS)
    if (issue) {
      // One sentence, and the link field, which is the way round both a
      // file too big for the bucket and one of a kind it does not take. An
      // iPhone's HEIC keeps its own sentence: it is the phone's setting, not
      // the file, that has to change.
      setFileIssue(
        issue.kind === "size"
          ? t("assignment.file.tooLarge", { maxMb: maxMb(SUBMISSIONS) })
          : issue.kind === "heic"
            ? issue.message
            : t("assignment.file.unsupported"),
      )
      setLinkShown(true)
      return
    }
    setFile({ state: "uploading", name: chosen.name, size: chosen.size, progress: 0 })
    try {
      const uploaded = await storageService.uploadSubmissionFile(
        courseId,
        assignment.id,
        user.id,
        chosen,
        (fraction) =>
          setFile((f) => (f?.state === "uploading" ? { ...f, progress: fraction } : f)),
      )
      setFile({ state: "ready", name: chosen.name, size: chosen.size, bucket: uploaded.bucket, path: uploaded.path })
    } catch (error: unknown) {
      setFile({ state: "failed", name: chosen.name, size: chosen.size, message: describeUploadError(error, SUBMISSIONS) })
    }
  }

  const removeFile = () => {
    if (file?.state === "ready") {
      // Best-effort: an orphan in the bucket is nothing the student needs
      // to hear about.
      void storageService.removeSubmissionFile(file.path).catch(() => undefined)
    }
    setFile(null)
  }

  const hasWork = Boolean(content.trim() || fileUrl.trim() || file?.state === "ready")
  const canSubmit =
    hasWork &&
    !submitting &&
    file?.state !== "uploading" &&
    (!declarationNeeded || declaration.aiUse !== null)

  const handleSubmit = async () => {
    if (!canSubmit) return
    setSubmitting(true)
    const landed = (sub: AssignmentSubmission) => {
      setSubmission(sub)
      setContent("")
      setFileUrl("")
      setFile(null)
      setLinkShown(false)
      setFileIssue(null)
      setDeclaration(BLANK_DECLARATION)
      clearDraft()
      onSubmitted?.()
    }
    try {
      landed(
        await coursesService.submitAssignment(assignment.id, {
          content: content.trim() || undefined,
          file_url: fileUrl.trim() || undefined,
          file: file?.state === "ready" ? { path: file.path, name: file.name } : undefined,
          declaration:
            declarationNeeded && declaration.aiUse !== null
              ? {
                  ai_use: declaration.aiUse,
                  // The text as displayed, not a pointer to it.
                  statement: declarationStatement(policy, declaration.aiUse, t),
                  note: declaration.aiUse === "assisted" ? declaration.note.trim() || undefined : undefined,
                }
              : undefined,
        }),
      )
    } catch (error: unknown) {
      // No answer at all: the work may be on the server already, and a
      // second press would hand it in twice. Ask before saying it failed.
      if (answerWasLost(error)) {
        // The panel holds only the latest submission, so the history's
        // earlier copies are «unseen» too: only a row newer than the one on
        // screen can be the request's own.
        const known = new Set(submission ? [submission.id] : [])
        const rows = await coursesService.getMySubmissions(assignment.id).catch(() => null)
        const mine = rows && newestUnseen(rows, known, (r) => r.submitted_at, submission?.submitted_at)
        if (mine) {
          landed(mine)
          setSubmitting(false)
          return
        }
      }
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

  // Overdue is about work not handed in. Work handed in before the date
  // read «Overdue» in red the day after (2026-10-03).
  const isOverdue = !submission && assignment.due_date && new Date(assignment.due_date) < new Date()

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
    <div className="rounded-card border border-edge dark:border-transparent bg-card shadow-card">
      <div className="border-b border-edge px-5 py-5">
        {pageTitle === undefined && (
          <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
            <FileText className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            {t("assignment.eyebrow")}
          </p>
        )}
        {(pageTitle === undefined || !repeatsTitle(pageTitle, orNotTranslated(t, assignment.title))) && (
          <h2 className="font-serif text-lg font-semibold tracking-tight text-wrap-safe">
            {orNotTranslated(t, assignment.title)}
          </h2>
        )}
        {assignment.description && (
          <p className="prose-verse mt-1.5 text-sm leading-relaxed text-ink-muted text-wrap-safe whitespace-pre-line">
            {/* A cited verse opens over the page, as it does in a lesson. */}
            <ScriptureText text={asPlainText(assignment.description)} />
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
                {formatDateTimeZoned(assignment.due_date)}
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
            {/* «Оценено» above «Оценка 90 / 100» said it twice: the grade is
                the status. */}
            {!(submission.status === "graded" && submission.grade !== null) && (
              <div className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm ${statusConfig[submission.status]?.color ?? ""}`}>
                {statusConfig[submission.status]?.icon}
                <span className="font-medium">{statusConfig[submission.status]?.label}</span>
                {submission.is_late && <LateBadge className="ml-auto" />}
              </div>
            )}
            {/* The deadline was shown above the work and never consulted when
                the work arrived (2026-10-03). Said once, beside the grade when
                the status row has given way to it. */}
            {submission.is_late && submission.status === "graded" && submission.grade !== null && (
              <div>
                <LateBadge />
              </div>
            )}

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

            {(submission.content || submission.file_path) && (
              <div className="rounded-md bg-muted/20 p-4">
                <p className="mb-1.5 text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
                  {t("assignment.yourSubmission")}
                </p>
                {submission.content && (
                  <p className="text-sm leading-relaxed text-wrap-safe whitespace-pre-wrap">{submission.content}</p>
                )}
                {submission.file_bucket && submission.file_path && submission.file_name && (
                  <SubmissionFileChip
                    bucket={submission.file_bucket}
                    path={submission.file_path}
                    name={submission.file_name}
                    className={submission.content ? "mt-3" : ""}
                  />
                )}
              </div>
            )}
          </div>
        )}

        {showForm && (
          <div className="space-y-4">
            {canResubmit && (
              <div className="rounded-md border border-warning/30 border-l-stripe border-l-warning bg-warning/10 px-3 py-2 text-xs font-medium text-warning-ink">
                {t("assignment.returnedHint")}
              </div>
            )}
            <div className="space-y-1.5">
              <Label htmlFor={`answer-${assignment.id}`} className="text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
                {t("assignment.yourResponse")}
              </Label>
              <Textarea
                id={`answer-${assignment.id}`}
                fieldSize="default"
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder={t("assignment.responsePlaceholder")}
                className="min-h-[120px] leading-relaxed"
              />
              {/* Quiet, and only once there is something to say. A student who
                  has typed one word does not need reassurance; one who comes
                  back to find their essay still there needs to know why. */}
              {(restored !== null || savedAt !== null) && (
                <p className="text-xs text-ink-muted" role="status">
                  {restored ? t("assignment.draftRestored") : t("assignment.draftSaved")}
                </p>
              )}
            </div>

            {/* The file. One large button; the phone offers the camera, the
                gallery and the files behind it, and the upload starts the
                moment a file is chosen so that «Отправить» has nothing left
                to wait for. */}
            <div className="space-y-2">
              <input
                ref={fileInput}
                type="file"
                accept={acceptAttribute(SUBMISSIONS)}
                className="sr-only"
                aria-label={t("assignment.file.attach")}
                tabIndex={-1}
                onChange={(e) => void chooseFile(e.target.files?.[0])}
              />
              {file === null ? (
                <Button
                  type="button"
                  variant="outline"
                  className="h-12 w-full justify-center text-base"
                  onClick={() => fileInput.current?.click()}
                >
                  <Paperclip className="mr-2 h-5 w-5" strokeWidth={1.75} aria-hidden />
                  {t("assignment.file.attach")}
                </Button>
              ) : (
                <div
                  className={`rounded-lg border px-3 py-2 ${
                    file.state === "failed" ? "border-destructive/40 bg-destructive/10" : "border-edge bg-surface"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {file.state === "uploading" ? (
                      <Loader2 className="h-4 w-4 shrink-0 animate-spin text-ink-muted" strokeWidth={1.75} aria-hidden />
                    ) : (
                      <Paperclip className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
                    )}
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">{file.name}</span>
                    <span className="shrink-0 text-xs tabular-nums text-ink-muted">
                      {t("assignment.file.sizeMb", { mb: formatNumber(file.size / MB, 1) })}
                    </span>
                    <button
                      type="button"
                      onClick={removeFile}
                      aria-label={t("assignment.file.remove")}
                      className="-mr-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-ink-muted hover:bg-muted/40 hover:text-ink"
                    >
                      <X className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                    </button>
                  </div>
                  {file.state === "uploading" && (
                    <div
                      role="progressbar"
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={Math.round(file.progress * 100)}
                      aria-label={t("assignment.file.uploading")}
                      className="mt-2 h-1 overflow-hidden rounded-full bg-muted"
                    >
                      <div
                        className="h-full rounded-full bg-brand transition-[width] duration-200"
                        style={{ width: `${Math.max(2, Math.round(file.progress * 100))}%` }}
                      />
                    </div>
                  )}
                  {file.state === "failed" && (
                    <p className="mt-1.5 text-xs text-destructive-ink" role="alert">
                      {file.message}
                    </p>
                  )}
                </div>
              )}
              {fileIssue && (
                <p className="text-sm text-ink-muted" role="alert">
                  {fileIssue}
                </p>
              )}
              {linkShown ? (
                <Input
                  value={fileUrl}
                  onChange={(e) => setFileUrl(e.target.value)}
                  placeholder={t("assignment.fileLinkPlaceholder")}
                  aria-label={t("assignment.fileLinkOptional")}
                  inputMode="url"
                  fieldSize="default"
                />
              ) : (
                <button
                  type="button"
                  onClick={() => setLinkShown(true)}
                  className="min-h-11 text-sm text-ink-muted underline-offset-4 hover:text-ink hover:underline"
                >
                  {t("assignment.file.orPasteLink")}
                </button>
              )}
            </div>

            {/* Before the button, not after it: the reminder that was found to
                work in unproctored settings is one shown ahead of the act. */}
            <SubmissionDeclaration policy={policy} value={declaration} onChange={setDeclaration} />

            <div className="space-y-2">
              {declarationNeeded && (
                <p className="text-xs text-ink-muted">{t("declaration.bySubmitting")}</p>
              )}
              <Button onClick={handleSubmit} disabled={!canSubmit} className="h-12 w-full text-base sm:w-auto">
                {submitting ? (
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" strokeWidth={1.75} aria-hidden />
                ) : (
                  <Send className="mr-2 h-5 w-5" strokeWidth={1.75} aria-hidden />
                )}
                {submitting ? t("assignment.submitting") : canResubmit ? t("assignment.resubmit") : t("assignment.submit")}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
