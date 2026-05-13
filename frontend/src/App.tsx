import { lazy, Suspense } from "react"
import { BrowserRouter, Route, Navigate, useLocation } from "react-router-dom"
import { Trans, useTranslation } from "react-i18next"
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

const NotFound = lazy(() => import("./pages/NotFound"))

const Login = lazy(() => import("./pages/Auth/Login"))
const Register = lazy(() => import("./pages/Auth/Register"))
const ForgotPassword = lazy(() => import("./pages/Auth/ForgotPassword"))
const ResetPassword = lazy(() => import("./pages/Auth/ResetPassword"))
const AuthCallback = lazy(() => import("./pages/Auth/AuthCallback"))
const HomePage = lazy(() => import("./pages/Home/HomePage"))
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
const CalendarPage = lazy(() => import("./pages/Calendar/CalendarPage"))

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

function PendingTeacherBanner() {
  const { t } = useTranslation()
  return (
    <div className="border-b border-border border-l-[3px] border-l-warning bg-warning/10">
      <div className="container mx-auto px-4 py-3 text-center">
        <p className="text-sm text-foreground">
          {t("pendingTeacher.banner")}{" "}
          <Trans
            i18nKey="pendingTeacher.contactSupport"
            components={{
              supportLink: (
                <a
                  href="mailto:support@bibleschool.com"
                  className="underline font-medium hover:no-underline"
                />
              ),
            }}
          />
        </p>
      </div>
    </div>
  )
}

const AUTH_PATHS = ["/login", "/register", "/forgot-password", "/auth/reset-password", "/auth/callback", "/auth/confirm"]

function AppRoutes() {
  const { user, loading } = useAuth()
  const location = useLocation()
  const { t } = useTranslation()
  const isAuthPage = AUTH_PATHS.some((p) => location.pathname.startsWith(p))
  usePageTitle()
  useLocaleSync()

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
    <div className="min-h-screen flex flex-col bg-background text-foreground">
      <Header />
      {user?.role === "pending_teacher" && <PendingTeacherBanner />}
      <AnnouncementBanner />
      <main className="flex-1">
        <ErrorBoundary>
          <Suspense fallback={<PageSpinner />}>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/dashboard" element={<Navigate to="/" replace />} />
              <Route path="/profile" element={<Gate mode="private"><ProfilePage /></Gate>} />
              <Route path="/calendar" element={<Gate mode="private"><CalendarPage /></Gate>} />
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
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </main>
      <Footer />
      <ScrollToTop />
      <Toaster />
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
