import { Link, useLocation } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { BookOpen, CalendarDays, GraduationCap, House, User as UserIcon, type LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"
import { toProxyImage } from "@/lib/images"
import type { User } from "@/types"

interface Tab {
  to: string
  label: string
  icon: LucideIcon
  active: boolean
}

/**
 * The phone's navigation: a bar of icons along the bottom, where a thumb
 * already is — «на телефоне больше иконок, меньше текста».
 *
 * Until 2026-09-28 a phone reached every section through the menu button
 * in the top corner: two taps and a sheet of words for what a desktop
 * does with one click. Every learning app a student here also uses
 * (Duolingo, YouVersion, their bank) puts the handful of places at the
 * bottom as icons, and that is where people look.
 *
 * Signed-in only, below `md` only. The labels stay, small: an icon alone
 * is a guess for anybody who has not used the app for a week. The menu
 * button keeps what is used rarely (admin, sign-out, settings).
 */
export function MobileTabBar({ user, isTeacher }: { user: User; isTeacher: boolean }) {
  const { t } = useTranslation()
  const { pathname } = useLocation()
  const under = (prefix: string) => pathname === prefix || pathname.startsWith(`${prefix}/`)

  const tabs: Tab[] = [
    { to: "/", label: t("header.home"), icon: House, active: pathname === "/" },
    { to: "/courses", label: t("header.courses"), icon: BookOpen, active: under("/courses") },
    { to: "/calendar", label: t("header.calendar"), icon: CalendarDays, active: under("/calendar") },
    ...(isTeacher
      ? [{ to: "/teacher", label: t("header.manage"), icon: GraduationCap, active: under("/teacher") }]
      : []),
    { to: "/profile", label: t("header.profile"), icon: UserIcon, active: under("/profile") },
  ]

  return (
    <nav
      aria-label={t("header.mobileTabs")}
      className="fixed inset-x-0 bottom-0 z-40 border-t border-edge bg-surface pb-[env(safe-area-inset-bottom)] shadow-[0_-8px_24px_-16px_hsl(30_10%_12%/0.18)] md:hidden dark:shadow-[0_-8px_24px_-12px_hsl(0_0%_0%/0.6)]"
    >
      <ul className="mx-auto flex max-w-md items-stretch justify-around px-2">
        {tabs.map(({ to, label, icon: Icon, active }) => (
          <li key={to} className="flex-1">
            <Link
              to={to}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex min-h-[56px] flex-col items-center justify-center gap-0.5 text-[10px] font-medium leading-none transition-colors duration-fast",
                active ? "text-ink" : "text-ink-muted hover:text-ink",
              )}
            >
              <span
                className={cn(
                  "flex h-7 w-12 items-center justify-center rounded-full transition-colors duration-base",
                  active && "bg-muted",
                )}
              >
                {to === "/profile" && user.avatar_url ? (
                  <img
                    src={toProxyImage(user.avatar_url)}
                    alt=""
                    className={cn("h-5 w-5 rounded-full object-cover", active && "ring-2 ring-ink/70")}
                  />
                ) : (
                  <Icon className="h-5 w-5" strokeWidth={active ? 2 : 1.75} aria-hidden />
                )}
              </span>
              <span className="max-w-full truncate px-0.5">{label}</span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  )
}
