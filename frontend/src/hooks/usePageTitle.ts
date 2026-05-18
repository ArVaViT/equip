import { useEffect } from "react"
import { useLocation } from "react-router-dom"

const BASE = "Bible School LMS"

const TITLES: Record<string, string> = {
  "/login": "Sign In",
  "/register": "Create Account",
  "/forgot-password": "Forgot Password",
  "/auth/reset-password": "Reset Password",
  "/auth/callback": "Authenticating…",
  "/auth/confirm": "Confirming Email…",
  "/dashboard": "Courses",
  "/profile": "My Profile",
  "/certificates": "My Certificates",
  "/calendar": "Calendar",
  "/teacher": "Teacher Dashboard",
  "/admin": "Admin Panel",
  "/": "Home",
}

function matchTitle(pathname: string): string {
  if (TITLES[pathname]) return TITLES[pathname]

  if (/^\/teacher\/courses\/[^/]+\/modules\/[^/]+\/chapters\/[^/]+\/edit$/.test(pathname)) return "Edit Chapter"
  if (/^\/teacher\/courses\/[^/]+\/modules\/[^/]+\/edit$/.test(pathname)) return "Edit Module"
  if (/^\/teacher\/courses\/[^/]+\/gradebook$/.test(pathname)) return "Gradebook"
  if (/^\/teacher\/courses\/[^/]+\/progress$/.test(pathname)) return "Student Progress"
  if (/^\/teacher\/courses\/[^/]+\/analytics$/.test(pathname)) return "Course Analytics"
  if (pathname.startsWith("/teacher/courses/")) return "Course Editor"
  if (/^\/courses\/[^/]+\/modules\/[^/]+\/chapters\/[^/]+$/.test(pathname)) return "Chapter"
  if (/^\/courses\/[^/]+\/modules\//.test(pathname)) return "Module"
  if (pathname.startsWith("/courses/")) return "Course"
  if (pathname.startsWith("/admin")) return "Admin Panel"

  return ""
}

export function usePageTitle() {
  const { pathname } = useLocation()

  useEffect(() => {
    const sub = matchTitle(pathname)
    document.title = sub ? `${sub} — ${BASE}` : BASE
  }, [pathname])
}
