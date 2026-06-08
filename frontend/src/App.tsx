import { lazy, Suspense } from "react"
import { BrowserRouter, Route, Navigate, useLocation } from "react-router-dom"
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
import Footer from "./components/layout/Footer"
import AnnouncementBanner from "./components/announcements/AnnouncementBanner"
import PageSpinner from "./components/ui/PageSpinner"
import ScrollToTop from "./components/layout/ScrollToTop";
import { TooltipProvider } from "@/components/ui/tooltip"
import { useGrandTour } from "@/hooks/useGrandTour"

// Lazy: FirstRunFlow renders null until a brand-new user's privacy/setup gate
// activates, so it never needs to be on the critical path — and it (plus its
// framer-motion dependency) is dead weight in the eager entry chunk for the
// 99% of loads that are returning/anonymous users. Suspense fallback is null
// because "not loaded yet" is visually identical to its own inactive state.
const FirstRunFlow = lazy(() =>
  import("@/components/firstRun").then((m) => ({ default: m.FirstRunFlow })),
)

const NotFound = lazy(() => import("./pages/NotFound"))

const Login = lazy(() => import("./pages/Auth/Login"))
const Register = lazy(() => import("./pages/Auth/Register"))
const ForgotPassword = lazy(() => import("./pages/Auth/ForgotPassword"))
const ResetPassword = lazy(() => import("./pages/Auth/ResetPassword"))
const AuthCallback = lazy(() => import("./pages/Auth/AuthCallback"))
const DashboardPage = lazy(() => import("./pages/Dashboard/DashboardPage"))
const CoursesPage = lazy(() => import("./pages/Courses/CoursesPage"))
const ProfilePage = lazy(() => import("./pages/Profile/ProfilePage"))
const CourseDetail = lazy(() => import("./pages/Course/CourseDetail"))
const ModuleView = lazy(() => import("./pages/Course/ModuleView"))
const TeacherDashboard = lazy(() => import("./pages/Teacher/TeacherDashboard"))
const CertificatesPage = lazy(() => import("./pages/Certificates/CertificatesPage"))
const CourseEditor = lazy(() => import("./pages/Teacher/CourseEditor"))
const ModuleEditor = lazy(() => import("./pages/Teacher/ModuleEditor"))
const TeacherGradebook = lazy(() => import("./pages/Teacher/TeacherGradebook"))
const TeacherAnalytics = lazy(() => import("./pages/Teacher/TeacherAnalytics"))
const StudentProgress = lazy(() => import("./pages/Teacher/StudentProgress"))
const ChapterView = lazy(() => import("./pages/Course/ChapterView"))
const ChapterEditor = lazy(() => import("./pages/Teacher/ChapterEditor"))
const AdminDashboard = lazy(() => import("./pages/Admin/AdminDashboard"))
const CohortDetailPage = lazy(() => import("./pages/Admin/cohorts/CohortDetailPage"))
const CalendarPage = lazy(() => import("./pages/Calendar/CalendarPage"))
const DailyChallengeArchivePage = lazy(() => import("./pages/DailyChallengeArchive/DailyChallengeArchivePage"))
const DailyChallengeReviewPage = lazy(() => import("./pages/Admin/dailyChallenge/DailyChallengeReviewPage"))
const DailyChallengeReviewDetailPage = lazy(() => import("./pages/Admin/dailyChallenge/DailyChallengeReviewDetailPage"))

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

const AUTH_PATHS = ["/login", "/register", "/forgot-password", "/auth/reset-password", "/auth/callback", "/auth/confirm"]

function AppRoutes() {
  const { loading } = useAuth()
  const location = useLocation()
  const { t } = useTranslation()
  const isAuthPage = AUTH_PATHS.some((p) => location.pathname.startsWith(p))
  usePageTitle()
  useLocaleSync()
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
              <Route path="/teacher/courses/:courseId/gradebook" element={<Gate mode="teacher"><TeacherGradebook /></Gate>} />
              <Route path="/teacher/courses/:courseId/progress" element={<Gate mode="teacher"><StudentProgress /></Gate>} />
              <Route path="/admin" element={<Gate mode="admin"><AdminDashboard /></Gate>} />
              <Route path="/admin/cohorts/:cohortId" element={<Gate mode="admin"><CohortDetailPage /></Gate>} />
              <Route path="/admin/daily-challenge/review" element={<Gate mode="teacher"><DailyChallengeReviewPage /></Gate>} />
              <Route path="/admin/daily-challenge/review/:questionId" element={<Gate mode="teacher"><DailyChallengeReviewDetailPage /></Gate>} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </main>
      <Footer />
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
