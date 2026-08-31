import { Suspense, useEffect, useRef } from "react"
import { lazyRoute } from "@/lib/lazyRoute"
import { BrowserRouter, Route, Navigate, useLocation, useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Routes } from "@datadog/browser-rum-react/react-router-v6"
import { AuthProvider } from "./context/AuthContext"
import { ThemeProvider } from "./context/ThemeContext"
import { useAuth } from "./context/useAuth"
import { usePageTitle } from "./hooks/usePageTitle"
import { useLocaleSync } from "./i18n/useLocaleSync"
import ErrorBoundary from "./components/ErrorBoundary"
import { Toaster } from "./components/ui/sonner"
import { ConfirmProvider } from "./components/ui/alert-dialog"
import Header from "./components/layout/Header"
import AnnouncementBanner from "./components/announcements/AnnouncementBanner"
import PageSpinner from "./components/ui/PageSpinner"
import ScrollToTop from "./components/layout/ScrollToTop";
import { TooltipProvider } from "@/components/ui/tooltip"
import { useGrandTour } from "@/hooks/useGrandTour"
import { takePendingInviteToken } from "@/lib/pendingInvite"

// Lazy: FirstRunFlow renders null until a brand-new user's privacy/setup gate
// activates, so it never needs to be on the critical path — its component code
// is dead weight in the eager entry chunk for the 99% of loads that are
// returning/anonymous users. (Note: this does NOT keep framer-motion itself
// out of the entry chunk — the bundler hoists motion into `index` because
// several lazy routes share it; see PressFeedback/CourseCard/DashboardPage.)
// Suspense fallback is null because "not loaded yet" is visually identical to
// its own inactive state.
const FirstRunFlow = lazyRoute(() =>
  import("@/components/firstRun").then((m) => ({ default: m.FirstRunFlow })),
)

const NotFound = lazyRoute(() => import("./pages/NotFound"))

const Login = lazyRoute(() => import("./pages/Auth/Login"))
const Register = lazyRoute(() => import("./pages/Auth/Register"))
const ForgotPassword = lazyRoute(() => import("./pages/Auth/ForgotPassword"))
const ResetPassword = lazyRoute(() => import("./pages/Auth/ResetPassword"))
const AuthCallback = lazyRoute(() => import("./pages/Auth/AuthCallback"))
const AcceptInvite = lazyRoute(() => import("./pages/Invite/AcceptInvite"))
const DashboardPage = lazyRoute(() => import("./pages/Dashboard/DashboardPage"))
const CoursesPage = lazyRoute(() => import("./pages/Courses/CoursesPage"))
const VerifyCertificatePage = lazyRoute(() => import("./pages/Verify/VerifyCertificatePage"))
const LegalDocumentPage = lazyRoute(() => import("./pages/Legal/LegalDocumentPage"))
const ProfilePage = lazyRoute(() => import("./pages/Profile/ProfilePage"))
const CourseDetail = lazyRoute(() => import("./pages/Course/CourseDetail"))
const ModuleView = lazyRoute(() => import("./pages/Course/ModuleView"))
const TeacherDashboard = lazyRoute(() => import("./pages/Teacher/TeacherDashboard"))
const CertificatesPage = lazyRoute(() => import("./pages/Certificates/CertificatesPage"))
const CourseEditor = lazyRoute(() => import("./pages/Teacher/CourseEditor"))
const ModuleEditor = lazyRoute(() => import("./pages/Teacher/ModuleEditor"))
const VedomostPage = lazyRoute(() => import("./pages/Teacher/vedomost/VedomostPage"))
const TeacherGradebook = lazyRoute(() => import("./pages/Teacher/TeacherGradebook"))
const GradingQueue = lazyRoute(() => import("./pages/Teacher/GradingQueue"))
const CertificateDocument = lazyRoute(() => import("./pages/Certificates/CertificateDocument"))
const TeacherAnalytics = lazyRoute(() => import("./pages/Teacher/TeacherAnalytics"))
const StudentProgress = lazyRoute(() => import("./pages/Teacher/StudentProgress"))
const ChapterView = lazyRoute(() => import("./pages/Course/ChapterView"))
const ChapterEditor = lazyRoute(() => import("./pages/Teacher/ChapterEditor"))
const AdminDashboard = lazyRoute(() => import("./pages/Admin/AdminDashboard"))
const CohortDetailPage = lazyRoute(() => import("./pages/Admin/cohorts/CohortDetailPage"))
const CalendarPage = lazyRoute(() => import("./pages/Calendar/CalendarPage"))
const DailyChallengeArchivePage = lazyRoute(() => import("./pages/DailyChallengeArchive/DailyChallengeArchivePage"))
const DailyChallengeReviewPage = lazyRoute(() => import("./pages/Admin/dailyChallenge/DailyChallengeReviewPage"))
const DailyChallengeReviewDetailPage = lazyRoute(() => import("./pages/Admin/dailyChallenge/DailyChallengeReviewDetailPage"))

/**
 * a11y: after a client-side route change, move keyboard / screen-reader
 * focus to the ``#main-content`` landmark so the next Tab starts inside
 * the freshly-rendered page instead of wherever the clicked link left
 * it (often back at the top of the persistent Header). The initial mount
 * is skipped — a hard page load already lands focus at the document
 * start, and stealing it on first paint would fight the skip-link and
 * any autofocused field. ``preventScroll`` so focusing the landmark
 * doesn't yank the viewport; ``ScrollToTop`` owns scroll position.
 */
function useRouteFocus() {
  const { pathname } = useLocation()
  const isInitialMount = useRef(true)
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false
      return
    }
    const main = document.getElementById("main-content")
    main?.focus({ preventScroll: true })
  }, [pathname])
}

type RouteMode = "private" | "public" | "teacher" | "admin"

function Gate({ mode, children }: { mode: RouteMode; children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <PageSpinner />
  if (mode === "public") {
    return user ? <Navigate to="/" replace /> : <>{children}</>
  }
  if (!user) return <Navigate to="/login" replace />
  if (mode === "teacher" && user.role !== "teacher" && user.role !== "admin") {
    return <Navigate to="/" replace />
  }
  if (mode === "admin" && user.role !== "admin") {
    return <Navigate to="/" replace />
  }
  return <>{children}</>
}

const AUTH_PATHS = [
  "/login",
  "/register",
  "/forgot-password",
  "/auth/reset-password",
  "/auth/callback",
  "/auth/confirm",
  "/invite/accept",
]

/**
 * Resumes an in-progress invite redemption after a full-page redirect
 * (Google OAuth, or clicking the "confirm your email" link) lands the
 * visitor back on the app authenticated but on an unrelated route.
 * AcceptInvite persists the token via `setPendingInviteToken` right
 * before either redirect kicks off; this picks it up once `user`
 * becomes non-null and finishes the trip back to `/invite/accept`.
 * `takePendingInviteToken` clears the stored value on read, so this is
 * naturally a no-op on every render after the first.
 */
function useResumePendingInvite() {
  const { user } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  useEffect(() => {
    if (!user) return
    if (location.pathname === "/invite/accept") return
    const token = takePendingInviteToken()
    if (token) navigate(`/invite/accept?token=${encodeURIComponent(token)}`, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id])
}

function AppRoutes() {
  const { loading } = useAuth()
  const location = useLocation()
  const { t } = useTranslation()
  const isAuthPage = AUTH_PATHS.some((p) => location.pathname.startsWith(p))
  usePageTitle()
  useLocaleSync()
  useRouteFocus()
  useResumePendingInvite()
  // Grand tour lives here so it has access to React Router (for
  // programmatic navigation between steps) and AuthContext (for the
  // role gate). Mounts after auth is resolved; the hook itself gates
  // on userId so a logged-out render is a no-op. Don't mount it on
  // auth pages — the user isn't signed in there.
  useGrandTour()

  if (loading) {
    return <PageSpinner variant="screen" label={t("common.loading")} />
  }

  if (isAuthPage) {
    return (
      <ErrorBoundary>
        <Suspense fallback={<PageSpinner />}>
          <Routes>
            <Route path="/login" element={<Gate mode="public"><Login /></Gate>} />
            <Route path="/register" element={<Gate mode="public"><Register /></Gate>} />
            <Route path="/forgot-password" element={<Gate mode="public"><ForgotPassword /></Gate>} />
            <Route path="/auth/reset-password" element={<ResetPassword />} />
            <Route path="/auth/callback" element={<AuthCallback />} />
            <Route path="/auth/confirm" element={<AuthCallback />} />
            {/* No <Gate> -- must render correctly for both an anonymous
                visitor (fresh invite link) and an authenticated one
                (bounced back here after Google OAuth / email confirm). */}
            <Route path="/invite/accept" element={<AcceptInvite />} />
            <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
        </Suspense>
      </ErrorBoundary>
    )
  }

  return (
    <div className="min-h-screen flex flex-col bg-surface text-ink">
      {/* Skip link — hidden until focused via Tab. First focusable element on
          every authenticated page so keyboard / screen-reader users can jump
          past the persistent Header + banners straight to page content. */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-md focus:bg-brand focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-brand-foreground focus:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
      >
        {t("common.skipToContent")}
      </a>
      <Header />
      <AnnouncementBanner />
      {/* ``min-h-[calc(100dvh-header)]`` keeps the footer permanently below
          the initial viewport on every authenticated page — you only see it
          after deliberately scrolling. ``100dvh`` (not ``100vh``) so the
          mobile browser chrome's collapsing toolbar doesn't shift the
          footer into view mid-scroll. Header height: ``h-11`` (2.75rem)
          on mobile, ``md:h-12`` (3rem) from md up. Optional
          banners (Announcement) take their own space
          above main, which means with a banner active the visible
          main is slightly shorter — acceptable: the footer-below-fold
          contract still holds. */}
      <main
        id="main-content"
        tabIndex={-1}
        className="flex-1 focus:outline-none min-h-[calc(100dvh-2.75rem)] md:min-h-[calc(100dvh-3rem)]"
      >
        <ErrorBoundary>
          <Suspense fallback={<PageSpinner />}>
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/dashboard" element={<Navigate to="/" replace />} />
              <Route path="/courses" element={<CoursesPage />} />
              {/* Public. A policy you can only read after accepting it is not
                  a policy, and the consent checkbox has been naming these two
                  documents since long before they existed. */}
              {/* Public, and deliberately so: the reader is whoever was
                  handed the certificate. The number printed on every
                  certificate points here. */}
              <Route path="/verify" element={<VerifyCertificatePage />} />
              <Route path="/verify/:certificateNumber" element={<VerifyCertificatePage />} />
              <Route path="/privacy" element={<LegalDocumentPage slug="privacy" />} />
              <Route path="/terms" element={<LegalDocumentPage slug="terms" />} />
              <Route path="/profile" element={<Gate mode="private"><ProfilePage /></Gate>} />
              <Route path="/calendar" element={<Gate mode="private"><CalendarPage /></Gate>} />
              <Route path="/daily-challenge/archive" element={<Gate mode="private"><DailyChallengeArchivePage /></Gate>} />
              <Route path="/certificates" element={<Gate mode="private"><CertificatesPage /></Gate>} />
              <Route path="/courses/:id" element={<Gate mode="private"><CourseDetail /></Gate>} />
              <Route path="/courses/:courseId/modules/:moduleId" element={<Gate mode="private"><ModuleView /></Gate>} />
              <Route path="/courses/:courseId/modules/:moduleId/chapters/:chapterId" element={<Gate mode="private"><ChapterView /></Gate>} />
              <Route path="/teacher" element={<Gate mode="teacher"><TeacherDashboard /></Gate>} />
              <Route path="/teacher/courses/:courseId" element={<Gate mode="teacher"><CourseEditor /></Gate>} />
              <Route path="/teacher/courses/:courseId/modules/:moduleId/edit" element={<Gate mode="teacher"><ModuleEditor /></Gate>} />
              <Route path="/teacher/courses/:courseId/modules/:moduleId/chapters/:chapterId/edit" element={<Gate mode="teacher"><ChapterEditor /></Gate>} />
              <Route path="/teacher/courses/:courseId/analytics" element={<Gate mode="teacher"><TeacherAnalytics /></Gate>} />
              <Route path="/certificates/:certificateId" element={<Gate mode="private"><CertificateDocument /></Gate>} />
              <Route path="/teach/grading" element={<Gate mode="teacher"><GradingQueue /></Gate>} />
              <Route path="/teacher/courses/:courseId/gradebook" element={<Gate mode="teacher"><TeacherGradebook /></Gate>} />
              <Route path="/teacher/courses/:courseId/progress" element={<Gate mode="teacher"><StudentProgress /></Gate>} />
              <Route path="/teacher/courses/:courseId/vedomost" element={<Gate mode="teacher"><VedomostPage /></Gate>} />
              <Route path="/admin" element={<Gate mode="admin"><AdminDashboard /></Gate>} />
              <Route path="/admin/cohorts/:cohortId" element={<Gate mode="admin"><CohortDetailPage /></Gate>} />
              <Route path="/admin/daily-challenge/review" element={<Gate mode="teacher"><DailyChallengeReviewPage /></Gate>} />
              <Route path="/admin/daily-challenge/review/:questionId" element={<Gate mode="teacher"><DailyChallengeReviewDetailPage /></Gate>} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </main>
      {/* No footer in the application shell.
       *
       * There was an inverted colophon under every screen — a serif wordmark,
       * a tagline and a right-aligned link list, on the dashboard, inside a
       * chapter, under the grading queue. Vercel's dashboard has no footer.
       * Linear's app has no footer. Notion has no footer. A footer is a
       * marketing-page organ, and bolting one under an application is the
       * clearest way to make the application look like a 2013 website.
       *
       * `Footer` still exists and is rendered by `PublicLanding`, which is the
       * page it was written for. The two legal documents it used to carry are
       * now in the account menu, where a signed-in person would look for them
       * anyway. */}
      <ScrollToTop />
      <Toaster />
      {/* First-run gate: Privacy Policy + Quick Setup, blocking until
          the user accepts and finishes (or skips setup). Mounted
          after the main tree so its overlay sits above everything in
          DOM order; the explicit z-index in the component is the
          actual stacking source of truth. */}
      <Suspense fallback={null}>
        <FirstRunFlow />
      </Suspense>
    </div>
  )
}
export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <ConfirmProvider>
            <TooltipProvider>        
              <AppRoutes />
            </TooltipProvider>      
          </ConfirmProvider>
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  )
}
