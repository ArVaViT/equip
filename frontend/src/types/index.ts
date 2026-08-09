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
  grade: string | null
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
  /** Есть ли главы, предназначенные для оценивания. Глава типа «тест»
   *  существует сразу, а сам тест сохраняется только с вопросами — курс в
   *  процессе сборки имеет главы, но не имеет оцениваемых элементов. */
  has_gradable_chapters: boolean
  /** True when the effective weights differ from the configured ones, so the
   *  UI can explain why instead of showing a number that contradicts the
   *  settings page. */
  weights_redistributed: boolean
  /** `completion_pass` — the course has nothing gradable; `final_score` and
   *  `letter_grade` carry no meaning. */
  result_state: "graded" | "completion_pass" | "not_graded_yet" | "zero_weighted"
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
  completed_by: 'teacher' | 'self' | 'quiz' | null
  quiz_result: { score: number; max_score: number; passed: boolean } | null
  assignment_result: { status: string; grade: number | null; max_score: number } | null
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
  quiz_avg: number | null
  assignment_avg: number | null
  overall_grade: number | null
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

