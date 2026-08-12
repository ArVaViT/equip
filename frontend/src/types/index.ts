import type { ChapterType } from '@/lib/chapterTypes'

export type UserRole = 'admin' | 'teacher' | 'student'
type PreferredLocale = 'ru' | 'en'

/**
 * Single source of truth for role string literals. Use ``ROLES.ADMIN``
 * etc. instead of the bare ``"admin"`` everywhere — a typo in
 * ``"adimn"`` is caught by TypeScript at the call site, whereas the
 * bare string silently fails the role check.
 *
 * Mirrors the ``UserRole`` union (which mirrors the Pydantic
 * Literal that mirrors the Postgres CHECK constraint on
 * ``profiles.role``). All four representations stay in lockstep.
 */
export const ROLES = {
  ADMIN: 'admin',
  TEACHER: 'teacher',
  STUDENT: 'student',
} as const satisfies Record<string, UserRole>

export interface User {
  id: string
  email: string
  full_name: string | null
  avatar_url: string | null
  role: UserRole
  preferred_locale: PreferredLocale
  created_at: string
  updated_at: string
  // Present on the admin user-list rows; non-null when the account is
  // soft-deleted (deactivated). Optional because the current-user profile
  // shape doesn't always carry it.
  deactivated_at?: string | null
}

export interface Course {
  id: string
  title: string
  description: string | null
  image_url: string | null
  status: 'draft' | 'published'
  // Controls enrollment policy independently from `status` (ADR-010):
  // - 'public'    catalog enroll button works (subject to enrollment_start/end)
  // - 'institute' enroll button is shown disabled with the
  //              'Доступно только по приглашению' label
  access_mode: 'public' | 'institute'
  created_by: string
  created_at: string
  updated_at: string
  deleted_at: string | null
  enrollment_start: string | null
  enrollment_end: string | null
  modules?: Module[]
}

export interface Module {
  id: string
  course_id: string
  title: string
  description: string | null
  order_index: number
  due_date: string | null
  chapters?: Chapter[]
}

export interface Chapter {
  id: string
  module_id: string
  title: string
  order_index: number
  chapter_type: ChapterType
  requires_completion: boolean
  is_locked: boolean
}

export interface Enrollment {
  id: string
  user_id: string
  course_id: string
  cohort_id: string | null
  enrolled_at: string
  progress: number
  course?: Course
}

export interface StudentGrade {
  id: string
  student_id: string
  course_id: string
  /** Символ ручной оценки в схеме курса: «A», «5», «pass». Свободный текст
   *  больше не хранится — «Aa+» непредставимо (D7). */
  override_code: string | null
  /** Числовая ручная оценка — только для процентной схемы. */
  override_score: number | null
  /** Что насчитала система в момент простановки ручной оценки: оба числа
   *  показываются рядом, чтобы правка руками была видна как правка. */
  computed_score: number | null
  /** Необязательное обоснование, видно директору. */
  reason: string | null
  comment: string | null
  graded_by: string
  graded_at: string
  updated_at: string
}

export interface GradingConfig {
  quiz_weight: number
  assignment_weight: number
  participation_weight: number
}

export interface GradeBreakdown {
  quiz_avg: number
  quiz_weighted: number
  assignment_avg: number
  assignment_weighted: number
  participation_pct: number
  /** Retired as a weighted category (D5) — always 0, kept for wire compatibility. */
  participation_weighted: number
  final_score: number
  letter_grade: string
  /** Weights the score was actually computed from: an empty category drops out
   *  and hands its weight to the other one. Equal to the configured weights
   *  when both categories have items. */
  effective_quiz_weight: number
  effective_assignment_weight: number
  /** Содержит ли курс элементы каждого вида — отдельный факт от весов:
   *  задания могут быть, но пока ничего не весить, потому что не проверены. */
  has_quiz_items: boolean
  has_assignment_items: boolean
  /** Whether **this student** has at least one marked piece of work in each
   *  category. Separates "0% because they got it wrong" from "0% because
   *  nobody has read theirs" — identical arithmetic, opposite meanings, and
   *  only one of them belongs on a screen as a number. Per student, unlike the
   *  course-wide liveness that drives weight redistribution. */
  student_has_quiz_marks: boolean
  student_has_assignment_marks: boolean
  /** Есть ли главы, предназначенные для оценивания. Глава типа «тест»
   *  существует сразу, а сам тест сохраняется только с вопросами — курс в
   *  процессе сборки имеет главы, но не имеет оцениваемых элементов. */
  has_gradable_chapters: boolean
  /** True when the effective weights differ from the configured ones, so the
   *  UI can explain why instead of showing a number that contradicts the
   *  settings page. */
  weights_redistributed: boolean
  /** `completion_pass` — the course has nothing gradable; `final_score` and
   *  `letter_grade` carry no meaning.
   *  `not_assessed` — every item this student owed was excused, so there is no
   *  denominator left. Distinct from `completion_pass`: excusing an item also
   *  completes its chapter, so these students sit at progress 100 and reading
   *  them as "passed by completion" would certify a course nobody graded. */
  /** «Текущая» — the same marks over only the work that has been marked.
   *  `final_score` counts outstanding work as zero. Both, always as a pair
   *  (D10): one without the other is how a student and a teacher end up with
   *  two numbers neither can explain. */
  current_score: number
  current_letter_grade: string
  scores_differ: boolean
  result_state:
    | "graded"
    | "completion_pass"
    | "not_graded_yet"
    | "zero_weighted"
    | "not_assessed"
}

export interface StudentCalculatedGrade {
  student_id: string
  student_name: string | null
  student_email: string
  breakdown: GradeBreakdown
  manual_grade: string | null
}

export interface GradeSummaryResponse {
  course_id: string
  config: GradingConfig
  students: StudentCalculatedGrade[]
  /** How this course is graded, and the bands its symbols are read against —
   *  sent so the client renders from the school's own scale instead of a
   *  hardcoded copy of A–F. `[floor, symbol]`, highest floor first. */
  grading_scheme: string
  bands: [string, string][]
  /** null — усреднять нечего: курс без оцениваемого или ещё не проверенный. */
  class_average: number | null
}

export interface Announcement {
  id: string
  title: string
  content: string
  course_id: string | null
  created_by: string
  created_at: string
  updated_at: string
}

interface QuizOption {
  id: string
  question_id: string
  option_text: string
  is_correct?: boolean
  order_index: number
}

export type QuizQuestionType = 'multiple_choice' | 'true_false' | 'short_answer' | 'essay'

export interface QuizQuestion {
  id: string
  quiz_id: string
  question_text: string
  question_type: QuizQuestionType
  order_index: number
  points: number
  min_words: number | null
  options: QuizOption[]
}

export interface Quiz {
  id: string
  chapter_id: string
  title: string
  description: string | null
  quiz_type: 'quiz' | 'exam'
  max_attempts: number | null
  passing_score: number
  questions: QuizQuestion[]
  created_at: string
}

export interface QuizAnswerResult {
  id: string | null
  question_id: string
  selected_option_id: string | null
  text_answer: string | null
  is_correct: boolean | null
  points_earned: number
  grader_comment: string | null
  correct_option_id: string | null
}

export interface PendingAnswer {
  answer_id: string
  attempt_id: string
  question_id: string
  question_text: string
  question_type: QuizQuestionType
  max_points: number
  min_words: number | null
  text_answer: string | null
  points_earned: number
  grader_comment: string | null
  student_id: string
  student_name: string | null
  student_email: string
  submitted_at: string | null
}

export interface QuizAttempt {
  id: string
  quiz_id: string
  user_id: string
  score: number | null
  max_score: number | null
  passed: boolean | null
  started_at: string
  completed_at: string | null
  answers?: QuizAnswerResult[]
}

export interface Assignment {
  id: string
  chapter_id: string
  title: string
  description: string | null
  max_score: number
  due_date: string | null
  created_at: string
}

export interface AssignmentSubmission {
  id: string
  assignment_id: string
  student_id: string
  content: string | null
  file_url: string | null
  submitted_at: string
  status: 'submitted' | 'graded' | 'returned'
  grade: number | null
  feedback: string | null
  graded_by: string | null
  graded_at: string | null
}

export interface Certificate {
  id: string
  user_id: string
  course_id: string | null
  archived_course_title?: string | null
  issued_at: string | null
  certificate_number: string | null
  status: 'pending' | 'teacher_approved' | 'approved' | 'rejected'
  requested_at: string | null
  teacher_approved_at?: string | null
  teacher_approved_by?: string | null
  admin_approved_at?: string | null
  admin_approved_by?: string | null
  // Enrichment populated by the pending-cert listing endpoints
  // (teacher + admin panels); absent on the slim "/my" + course-detail
  // payloads. Optional because every other consumer ignores them.
  student_name?: string | null
  student_email?: string | null
  course_title?: string | null
  teacher_approver_name?: string | null
}

export type BlockType = 'text' | 'quiz' | 'assignment' | 'file'

export interface ChapterBlock {
  id: string
  chapter_id: string
  block_type: BlockType
  order_index: number
  content: string | null
  quiz_id: string | null
  assignment_id: string | null
  file_bucket: string | null
  file_path: string | null
  file_name: string | null
}

export interface CourseReview {
  id: string
  user_id: string
  course_id: string
  rating: number
  comment: string | null
  created_at: string
  reviewer_name?: string | null
}

export interface Cohort {
  id: string
  name: string
  start_date: string
  end_date: string
  enrollment_start: string | null
  enrollment_end: string | null
  // Mirrors backend `CohortStatus` literal + Postgres `cohorts_status_check`.
  // `archived` is in the type for completeness with the DB CHECK; no UX
  // sets it today.
  status: 'upcoming' | 'active' | 'completed' | 'archived'
  max_students: number | null
  created_by: string | null
  created_at: string
  updated_at: string | null
  // Computed on the server from cohort_courses + enrollments — see ADR-010.
  course_ids: string[]
  student_count: number
}

// InvitationRole deliberately excludes 'admin' -- mirrors the backend
// Pydantic Literal["teacher", "student"] and the Postgres CHECK
// constraint on invitations.role. An invite can never grant admin.
export type InvitationRole = 'teacher' | 'student'
export type InvitationStatus = 'pending' | 'accepted' | 'revoked'

export interface Invitation {
  id: string
  email: string
  role: InvitationRole
  status: InvitationStatus
  invited_by: string | null
  created_at: string | null
  accepted_at: string | null
  expires_at: string
  // Derived server-side: a 'pending' row past expires_at. Only
  // meaningful when status === 'pending'.
  is_expired: boolean
}

export type NotificationType =
  | 'certificate_approved'
  | 'certificate_rejected'
  | 'assignment_graded'
  | 'new_announcement'
  | 'course_update'
  | 'enrollment_confirmed'

export interface Notification {
  id: string
  user_id: string
  type: NotificationType
  title: string
  message: string
  link: string | null
  is_read: boolean
  created_at: string
  metadata: Record<string, unknown> | null
}

export interface NotificationListResponse {
  items: Notification[]
  total: number
  page: number
  page_size: number
}

export interface AuditLogEntry {
  id: string
  user_id: string | null
  action: string
  resource_type: string
  resource_id: string
  details: Record<string, unknown> | null
  ip_address: string | null
  user_agent: string | null
  created_at: string
}

export interface AuditLogPage {
  items: AuditLogEntry[]
  total: number
  page: number
  page_size: number
}

export interface Profile {
  id: string
  email: string
  full_name: string | null
  avatar_url: string | null
  role: UserRole
  preferred_locale: PreferredLocale
  created_at: string
  updated_at: string | null
}

type CalendarEventType = 'deadline' | 'live_session' | 'exam' | 'other'
type CalendarEventSource = 'module_deadline' | 'assignment_deadline' | 'course_event'

export interface CalendarEvent {
  id: string
  title: string
  description: string | null
  event_type: CalendarEventType
  event_date: string
  course_id: string
  course_title: string | null
  source: CalendarEventSource
}

export interface StudentChapterInfo {
  id: string
  title: string
  module_id: string
  chapter_type: ChapterType
  requires_completion: boolean
  completed: boolean
  /** How the chapter came to be complete. `excused` means a teacher waived the
   *  work — the tick is the same green as any other, so only this tells them
   *  apart, and a certificate gets signed on the difference. */
  completed_by: 'teacher' | 'self' | 'quiz' | 'excused' | null
  /** `awaiting_grading` — the attempt is in, but its open answers are still
   *  unread, so `score` is a running total and not a result. Rendering it as
   *  an ordinary mark shows a teacher a red 0% for work nobody has looked at. */
  quiz_result: {
    score: number
    max_score: number
    passed: boolean
    awaiting_grading?: boolean
  } | null
  assignment_result: { status: string; grade: number | null; max_score: number } | null
  /** The piece of work behind this chapter, present whether or not the student
   *  ever touched it — which is exactly when a teacher reaches for an
   *  exemption, and exactly when the result blocks above are null. */
  gradable_item: { type: 'quiz' | 'assignment'; id: string } | null
}

/** One waiver: this student does not owe this piece of work (D6). */
export interface GradeExemption {
  id: string
  student_id: string
  course_id: string
  item_type: 'quiz' | 'assignment'
  item_id: string
  reason: string | null
  created_by: string | null
  created_at: string | null
}

export interface StudentQuizResult {
  chapter_title: string
  chapter_id: string
  quiz_id: string
  score: number
  max_score: number
  passed: boolean
  attempts_used: number
}

export interface StudentAssignmentResult {
  chapter_title: string
  chapter_id: string
  title: string
  status: string
  grade: number | null
  max_score: number
}

/**
 * Lightweight per-student summary row for the progress-board LIST. The heavy
 * per-chapter breakdown + quiz/assignment result arrays are NOT here — they're
 * fetched per student via ``getStudentProgressDetail`` when a row expands. The
 * averages are computed server-side so the board never has to hold every
 * student's full result set in memory.
 */
export interface StudentProgressEntry {
  id: string
  full_name: string
  email: string
  enrolled_at: string | null
  progress: number
  chapters_completed: number
  total_chapters: number
  /** Category averages, present only once something in that category has
   *  actually been marked. `null` means "nobody has read it yet" — a distinct
   *  fact from 0%, which on a teacher's board reads as failure. */
  quiz_avg: number | null
  assignment_avg: number | null
  /** The official weighted grade, from the same service the gradebook uses
   *  (D14). `null` whenever `result_state` says there is no honest number. */
  overall_grade: number | null
  /** «Текущая» beside «итоговая» — see `GradeBreakdown.current_score`. */
  current_grade: number | null
  current_letter_grade: string | null
  scores_differ: boolean
  /** The hand-set grade, when a teacher set one. The override IS the official
   *  grade (D7), so it wins the display; the computed number stays beside it
   *  rather than being replaced, because seeing the pair is the point. */
  manual_grade: string | null
  result_state: GradeBreakdown["result_state"]
  letter_grade: string | null
  last_activity: string | null
}

/** Per-student detail fetched lazily on progress-board row expansion. */
export interface StudentProgressDetail {
  student_id: string
  chapters: StudentChapterInfo[]
  quiz_results: StudentQuizResult[]
  assignment_results: StudentAssignmentResult[]
}

/** One row of the gradebook spreadsheet: a student + their full chapter matrix. */
interface StudentGradebookEntry {
  id: string
  full_name: string
  email: string
  progress: number
  chapters_completed: number
  total_chapters: number
  chapters: StudentChapterInfo[]
}

/**
 * Full students x chapters matrix for the gradebook. Distinct from the slim
 * ``StudentProgressResponse`` (progress-board list) because the gradebook
 * renders every student against every chapter at once.
 */
export interface CourseGradebookMatrix {
  course_id: string
  course_title: string
  total_chapters: number
  total_students: number
  modules: { id: string; title: string; order_index: number }[]
  students: StudentGradebookEntry[]
}

export interface StudentProgressResponse {
  course_id: string
  course_title: string
  total_chapters: number
  total_students: number
  modules: { id: string; title: string; order_index: number }[]
  students: StudentProgressEntry[]
}

export interface CourseEvent {
  id: string
  course_id: string
  title: string
  description: string | null
  event_type: CalendarEventType
  event_date: string
  created_by: string
  created_at: string
}


/** One piece of work, as its owner sees it (D10.3). */
export interface MyGradeItem {
  /** The quiz or assignment itself. A chapter can hold two, so the chapter is
   *  not an identity. */
  item_id: string
  chapter_id: string
  title: string
  kind: "quiz" | "assignment"
  /** `pending_review` is the one that matters: an essay sits at 0 with
   *  `passed = false` from submission until somebody reads it, and a student
   *  shown that number concludes they failed work nobody has opened. */
  /** `returned` is not a variant of `pending_review`: pending work waits on
   *  the teacher, returned work waits on the student. A returned essay carries
   *  a grade, so without its own status it rendered as «проверено» while the
   *  course result said «незачёт». */
  status: "graded" | "pending_review" | "returned" | "not_submitted" | "excused"
  /** Present only for `graded`. A number on a pending row is the running
   *  total, which is precisely the thing being withheld. */
  score: number | null
}

/**
 * One reason a certificate is not available yet (D9).
 *
 * A code and numbers, never a sentence: the words live in the locale
 * catalogues, so adding a language is a translation change rather than a
 * backend release, and the student's card and the teacher's cannot word the
 * same obstacle differently.
 */
export interface CertificateBlocker {
  code: string
  params: Record<string, string | number | boolean>
  /** Where the work is. A refusal that names a problem without saying where it
   *  is sends the student to the teacher instead of to the work. */
  chapter_ids: string[]
}

/**
 * One thing that happened to a student's grade, and who did it.
 *
 * Teacher-facing only: `reason` is the note written about the student for the
 * institution (D7) and never reaches the student.
 */
export interface GradeHistoryEntry {
  id: string
  action: string
  at: string
  actor_id: string | null
  actor_name: string | null
  override_code: string | null
  override_score: string | null
  /** What the calculator said when the grade was set by hand. */
  computed_score: string | null
  reason: string | null
  item_type: string | null
  item_id: string | null
  blockers: string[]
}

/** One open «запросить пересдачу», as the teacher's course pages see it. */
export interface RetakeRequest {
  student_id: string
  requested_at: string | null
  /** What was blocking them when they asked, so the teacher arrives already
   *  knowing which of their four powers this calls for. */
  blockers: string[]
}

/** The answer to «запросить пересдачу». `already_requested` is not an error:
 *  the teacher already has the request. */
export interface RetakeRequestResult {
  status: "requested" | "already_requested"
}

/**
 * A student's own standing in one course.
 *
 * Carries no class average, no other student's name, no rank — absent from the
 * type rather than filtered out downstream, so putting one back would take a
 * deliberate change (D10.4). `comment` is the teacher's note *to* the student;
 * the `reason` on the same row is the note about them, written for the
 * institution, and never leaves the backend (D7).
 */
export interface MyCourseGrade {
  course_id: string
  grading_scheme: string
  pass_threshold: string
  progress: number
  current_score: number | null
  current_symbol: string | null
  final_score: number | null
  final_symbol: string | null
  scores_differ: boolean
  result_state: string
  /** True for a scheme whose rule is completion-based rather than arithmetic
   *  (`pass_fail`, D2) — the weighted percentage is not the result there. */
  scores_withheld: boolean
  /** For a completion-graded course, the verdict itself. No percentage sits
   *  behind it by design (D2): the rule is whether every required piece of
   *  work was accepted. */
  zachet: "zachet" | "nezachet" | "not_attested" | null
  official_grade: string | null
  comment: string | null
  /** Empty means nothing stands in the way. Shipped ahead of the gate that
   *  will enforce it, so no student meets a refusal they have never seen
   *  explained. */
  certificate_blockers: CertificateBlocker[]
  items: MyGradeItem[]
}

/** One line of a closed ведомость, as it was signed. */
export interface SheetRow {
  student_id: string
  /** The name the document was signed under — not the current one. */
  student_name: string | null
  result_state: "pass" | "fail" | "completion_pass" | "not_attested"
  official_code: string | null
  official_score: string | null
  /** Set by hand rather than computed — the director-visible glyph. */
  is_override: boolean
}

/**
 * A closed ведомость. Everything here came off the snapshot: the grades, the
 * names, the поток, the letterhead and the language. Nothing on this page is
 * looked up again, because a document whose words move after signature is not
 * a document.
 */
export interface GradeSheet {
  id: string
  course_id: string
  course_title: string | null
  locale: string
  cohort_id: string | null
  cohort_name: string | null
  cohort_start: string | null
  cohort_end: string | null
  school_name: string | null
  school_city: string | null
  teacher_name: string | null
  academic_hours: number | null
  grading_scheme: string
  pass_threshold: string | null
  finalized_at: string
  finalized_by: string | null
  reopened_at: string | null
  reopen_reason: string | null
  /** Set when this sheet replaced a reopened one — «была переоткрыта». */
  corrects_sheet_id: string | null
  correction_reason: string | null
  rows: SheetRow[]
}

/**
 * Work waiting on the teacher, counted once.
 *
 * Only their move: an unread open answer, a submitted assignment with no mark.
 * Work the student owes — never handed in, or handed back for revision — is
 * deliberately absent. A number a teacher cannot act on is a number they stop
 * reading.
 */
export interface PendingGrading {
  total: number
  by_course: Record<string, number>
}
