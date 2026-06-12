import { useTranslation } from "react-i18next"
import { useLocation } from "react-router-dom"
import { ROLES, type UserRole } from "@/types"
import { HeaderNavLink } from "./HeaderNavLink"

interface Props {
  isTeacher: boolean
  role: UserRole | undefined
}

/**
 * Top-bar primary navigation (>= md viewport). The labels here are
 * the COMPACT variants (``header.manage`` / ``header.admin``);
 * HeaderMobileSheet uses the VERBOSE variants
 * (``header.manageCourses`` / ``header.adminPanel``). Two keys per
 * destination is intentional — the bar is space-constrained, the
 * sheet has room. See ``UI-DECISIONS.md``.
 */
export function HeaderDesktopNav({ isTeacher, role }: Props) {
  const { t } = useTranslation()
  const location = useLocation()
  const isActive = (path: string) =>
    path === "/" ? location.pathname === "/" : location.pathname.startsWith(path)

  return (
    <nav
      data-tour="header-nav"
      className="hidden min-w-0 flex-1 flex-wrap items-stretch justify-center md:flex"
      aria-label={t("header.navAriaLabel")}
    >
      <HeaderNavLink to="/" active={location.pathname === "/"}>
        {t("header.home")}
      </HeaderNavLink>
      <HeaderNavLink to="/courses" active={isActive("/courses")}>
        {t("header.courses")}
      </HeaderNavLink>
      <HeaderNavLink to="/calendar" active={isActive("/calendar")}>
        {t("header.calendar")}
      </HeaderNavLink>
      <HeaderNavLink to="/certificates" active={isActive("/certificates")}>
        {t("header.certificates")}
      </HeaderNavLink>
      {isTeacher && (
        <HeaderNavLink to="/teacher" active={isActive("/teacher")}>
          {t("header.manage")}
        </HeaderNavLink>
      )}
      {role === ROLES.ADMIN && (
        <HeaderNavLink to="/admin" active={isActive("/admin")}>
          {t("header.admin")}
        </HeaderNavLink>
      )}
    </nav>
  )
}
