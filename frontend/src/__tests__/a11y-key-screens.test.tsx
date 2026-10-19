/**
 * axe over the screens a student and a teacher live on, rendered whole.
 *
 * The component-level suites (`ui/__tests__/a11y*.test.tsx`,
 * `components/__tests__/a11y-features.test.tsx`) prove each piece is clean
 * on its own; what they cannot see is how the pieces add up on a page — a
 * card whose h3 is fine under a section heading and a skipped level straight
 * under the page's h1, a `<dl>` whose pairs are wrapped one level too deep.
 * The 2026-10-19 pass found exactly those, on the catalog, the gradebook,
 * the progress board and the profile; this file is what would have caught
 * them.
 *
 * Each screen is also held to one h1 and an outline with no skipped level,
 * because jsdom lets axe see structure but not paint: colour contrast is
 * the contrast-audit script's job, and real landmarks the Playwright suite's.
 */
import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { axe, headingOutline } from "@/test/a11y"
import { ConfirmProvider } from "@/components/ui/alert-dialog"
import type { CalendarEvent, Chapter, ChapterBlock, Course, Enrollment, Module, User } from "@/types"

let authUser: User | null = null
vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({ user: authUser, loading: false, applyUser: vi.fn(), refreshUser: vi.fn(), logout: vi.fn() }),
}))
vi.mock("@/context/useTheme", () => ({ useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }) }))
vi.mock("@/hooks/useUserTour", () => ({ useUserTour: () => ({ start: vi.fn() }) }))
vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))

import { coursesService } from "@/services/courses"
import { gradesService } from "@/services/grades"
import { notesService } from "@/services/notes"
import { organizationsService } from "@/services/organizations"
import { storageService } from "@/services/storage"
import CoursesPage from "@/pages/Courses/CoursesPage"
import CourseDetail from "@/pages/Course/CourseDetail"
import ChapterView from "@/pages/Course/ChapterView"
import CalendarPage from "@/pages/Calendar/CalendarPage"
import ProfilePage from "@/pages/Profile/ProfilePage"
import StudentProgress from "@/pages/Teacher/StudentProgress"
import TeacherGradebook from "@/pages/Teacher/TeacherGradebook"

function Wrap({ children, at }: { children: ReactNode; at: string }) {
  return (
    <I18nextProvider i18n={i18n}>
      <ConfirmProvider>
        <MemoryRouter initialEntries={[at]}>{children}</MemoryRouter>
      </ConfirmProvider>
    </I18nextProvider>
  )
}

/** No axe violation, exactly one h1, and no level skipped on the way down. */
async function expectCleanPage(root: HTMLElement = document.body) {
  expect(await axe(root)).toHaveNoViolations()
  expect(root.querySelectorAll("h1")).toHaveLength(1)
  expect(headingOutline(root).gaps).toEqual([])
}

const student: User = {
  id: "u1", email: "anna@example.com", full_name: "Анна Петренко", avatar_url: null, role: "student",
  preferred_locale: "ru", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
  time_zone: "Europe/Berlin", time_zone_source: "detected", phone: null, birth_date: null,
  country_code: null, region: null, city: null, church: null,
} as User
const teacher: User = { ...student, id: "t1", role: "teacher", full_name: "Пётр Иванов" } as User

const chapter = (over: Partial<Chapter>): Chapter =>
  ({ course_id: "c1", module_id: null, order_index: 0, chapter_type: "reading", requires_completion: false, is_locked: false, ...over }) as Chapter
const module_ = (over: Partial<Module>): Module =>
  ({ course_id: "c1", description: null, order_index: 0, due_date: null, chapters: [], ...over }) as Module

const COURSE: Course = {
  id: "c1", title: "Деяния апостолов", description: "Путь церкви от Иерусалима до Рима.", image_url: null,
  status: "published", access_mode: "public", created_by: "t1", created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z", deleted_at: null, enrollment_start: null, enrollment_end: null,
  modules: [
    module_({
      id: "m1", title: "Начало", order_index: 0,
      chapters: [
        chapter({ id: "a1", module_id: "m1", title: "Пятидесятница", order_index: 0 }),
        chapter({ id: "a2", module_id: "m1", title: "Первая проповедь", order_index: 1, chapter_type: "quiz" }),
      ],
    }),
  ],
  chapters: [chapter({ id: "l1", title: "Антиохия", order_index: 2 })],
  chapter_count: 3, module_count: 1,
}

const ENROLLMENT: Enrollment = {
  id: "en1", user_id: "u1", course_id: "c1", cohort_id: null, enrolled_at: "2026-09-01T00:00:00Z",
  progress: 40, chapters_read: 1, chapters_to_read: 3, course: COURSE,
}

const EVENT: CalendarEvent = {
  id: "e1", title: "Занятие по Деяниям", description: null, event_type: "live_session",
  event_date: "2026-10-26T17:00:00Z", meeting_url: "https://zoom.us/j/1", recording_url: null,
  duration_minutes: 60, course_id: "c1", course_title: "Деяния апостолов", source: "course_event",
} as CalendarEvent

describe("key screens have no axe violations and a walkable outline", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru")
  })

  beforeEach(() => {
    vi.restoreAllMocks()
    authUser = student
    vi.spyOn(coursesService, "getMyCourses").mockResolvedValue([ENROLLMENT])
    vi.spyOn(coursesService, "getCourse").mockResolvedValue(COURSE)
    vi.spyOn(coursesService, "getCourseCohorts").mockResolvedValue([])
    vi.spyOn(coursesService, "getMyChapterProgress").mockResolvedValue(["a1"])
    vi.spyOn(coursesService, "getCalendarEvents").mockResolvedValue([EVENT])
    vi.spyOn(coursesService, "getMyCertificates").mockResolvedValue([])
    vi.spyOn(coursesService, "getTeacherCourses").mockResolvedValue([])
    vi.spyOn(storageService, "listCourseMaterials").mockResolvedValue([])
  })

  it("the catalog, with a section for the reader's organization", async () => {
    // Both levels a card can take: an h3 under the organization's h2 and
    // under «Open catalogue», and — on a catalog with no sections — an h2
    // straight under the page's h1 (CoursesPage.headings.test.tsx).
    vi.spyOn(coursesService, "getCourses").mockResolvedValue([COURSE])
    vi.spyOn(organizationsService, "mine").mockResolvedValue([{
      organization_id: "o1", organization_slug: "ucoat", organization_name: "UCOAT", role: "student",
      courses: [{ ...COURSE, id: "c2", title: "Курс проповеди", access_mode: "institute" }],
    }])
    render(<Wrap at="/courses"><CoursesPage /></Wrap>)
    await screen.findByRole("heading", { level: 3, name: "Курс проповеди" })
    await screen.findByRole("heading", { level: 3, name: "Деяния апостолов" })
    await expectCleanPage()
  })

  it("the course page, enrolled", async () => {
    vi.spyOn(coursesService, "getEnrollmentStatus").mockResolvedValue({ enrolled: true, enrollment: ENROLLMENT } as never)
    vi.spyOn(coursesService, "getCourseCertificate").mockResolvedValue(null as never)
    render(
      <Wrap at="/courses/c1">
        <Routes><Route path="/courses/:id" element={<CourseDetail />} /></Routes>
      </Wrap>,
    )
    await screen.findByRole("heading", { level: 1, name: "Деяния апостолов" })
    await screen.findAllByText("Начало")
    await expectCleanPage()
  })

  it("a lesson", async () => {
    vi.spyOn(coursesService, "getChapterBlocks").mockResolvedValue([
      {
        id: "b1", chapter_id: "a1", block_type: "text", order_index: 0,
        content: "<h2>Сошествие Духа</h2><p>В день Пятидесятницы все они были единодушно вместе.</p>",
      } as ChapterBlock,
    ])
    vi.spyOn(notesService, "get").mockResolvedValue({ chapter_id: "a1", body: "", updated_at: null })
    render(
      <Wrap at="/courses/c1/modules/m1/chapters/a1">
        <Routes>
          <Route path="/courses/:courseId/modules/:moduleId/chapters/:chapterId" element={<ChapterView />} />
        </Routes>
      </Wrap>,
    )
    await screen.findByRole("heading", { level: 1, name: "Пятидесятница" })
    await screen.findByText("Сошествие Духа")
    await expectCleanPage()
  })

  it("the calendar", async () => {
    render(<Wrap at="/calendar"><CalendarPage /></Wrap>)
    await screen.findByRole("heading", { level: 1 })
    await screen.findAllByText("Занятие по Деяниям")
    await expectCleanPage()
  })

  it("the profile, on the personal tab", async () => {
    const user = userEvent.setup()
    render(<Wrap at="/profile"><ProfilePage /></Wrap>)
    await screen.findByRole("heading", { level: 1 })
    await user.click(screen.getByRole("tab", { name: i18n.t("profile.tabs.personal") }))
    await screen.findByLabelText(i18n.t("profile.personal.phone"))
    await expectCleanPage()
  })

  it("the teacher's progress board", async () => {
    authUser = teacher
    vi.spyOn(coursesService, "getStudentProgress").mockResolvedValue({
      course_id: "c1", course_title: "Деяния апостолов", total_chapters: 3, total_students: 1, modules: [],
      students: [{
        id: "u1", full_name: "Анна Петренко", email: "anna@example.com", enrolled_at: "2026-09-20T00:00:00Z",
        progress: 40, chapters_completed: 1, total_chapters: 3, quiz_avg: 80, assignment_avg: null,
        overall_grade: null, current_grade: 80, current_letter_grade: "B", scores_differ: false,
        manual_grade: null, result_state: "not_graded_yet", letter_grade: null, last_activity: "2026-10-10T00:00:00Z",
      }],
    } as never)
    vi.spyOn(gradesService, "getRetakeRequests").mockResolvedValue([])
    render(
      <Wrap at="/teacher/courses/c1/progress">
        <Routes><Route path="/teacher/courses/:courseId/progress" element={<StudentProgress />} /></Routes>
      </Wrap>,
    )
    await screen.findByText("Анна Петренко")
    await expectCleanPage()
  })

  it("the teacher's gradebook", async () => {
    authUser = teacher
    vi.spyOn(coursesService, "getCourseGrades").mockResolvedValue([])
    vi.spyOn(coursesService, "getGradeSummary").mockResolvedValue({
      course_id: "c1", config: { quiz_weight: 40, assignment_weight: 40, participation_weight: 20 },
      grading_scheme: "letter", bands: [["90", "A"], ["80", "B"], ["70", "C"], ["0", "F"]], class_average: 88,
      students: [{
        student_id: "u1", student_name: "Анна Петренко", student_email: "anna@example.com", manual_grade: null,
        breakdown: {
          quiz_avg: 80, quiz_weighted: 32, assignment_avg: 90, assignment_weighted: 36, participation_pct: 100,
          participation_weighted: 20, final_score: 88, letter_grade: "B", effective_quiz_weight: 40,
          effective_assignment_weight: 40, has_quiz_items: true, has_assignment_items: true,
          student_has_quiz_marks: true, student_has_assignment_marks: true, has_gradable_chapters: true,
          weights_redistributed: false, current_score: 88, current_letter_grade: "B", scores_differ: false,
          result_state: "graded",
        },
      }],
    } as never)
    vi.spyOn(coursesService, "getGradebookMatrix").mockResolvedValue({ course_id: "c1", groups: [], students: [] } as never)
    render(
      <Wrap at="/teacher/courses/c1/gradebook">
        <Routes><Route path="/teacher/courses/:courseId/gradebook" element={<TeacherGradebook />} /></Routes>
      </Wrap>,
    )
    await screen.findByRole("heading", { level: 1 })
    await screen.findByText("Анна Петренко")
    await expectCleanPage()
  })
})
