import { lazy, Suspense } from "react"
import { Link, useLocation } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { User as UserIcon } from "lucide-react"
import { PressFeedback } from "@/components/motion"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { toProxyImage } from "@/lib/images"
import type { User } from "@/types"

const NotificationBell = lazy(() => import("../NotificationBell"))

const ICON_STROKE = 1.75 as const

interface Props {
  user: User | null
}

/**
 * Desktop-only (>= md) right-side cluster: notifications bell +
 * profile / avatar for authed users, sign-in / register for guests.
 *
 * The bell is lazy-loaded — its dropdown drags in dayjs locales and
 * the notification SDK, and unauthed home-page visitors should never
 * pay for that bundle.
 */
export function HeaderUserMenu({ user }: Props) {
  const { t } = useTranslation()
  const location = useLocation()
  const isProfileActive = location.pathname.startsWith("/profile")

  return (
    <div className="hidden items-center gap-1 md:flex">
      {user ? (
        <>
          <Suspense fallback={<div className="h-7 w-7 shrink-0" aria-hidden />}>
            <NotificationBell />
          </Suspense>
          <Tooltip>
            <TooltipTrigger asChild>
              <Link to="/profile" data-tour="header-profile" className="inline-flex">
                <PressFeedback className="inline-flex">
                  <Button
                    variant={isProfileActive ? "secondary" : "ghost"}
                    size="sm"
                    className="h-7 w-7 shrink-0 rounded-full p-0"
                    aria-label={t("header.profile")}
                  >
                    {user.avatar_url ? (
                      <img
                        src={toProxyImage(user.avatar_url)}
                        alt=""
                        className="h-6 w-6 rounded-full object-cover"
                        onError={(e) => {
                          e.currentTarget.style.display = "none"
                        }}
                      />
                    ) : (
                      <UserIcon
                        className="h-3.5 w-3.5"
                        strokeWidth={ICON_STROKE}
                        aria-hidden="true"
                      />
                    )}
                  </Button>
                </PressFeedback>
              </Link>
            </TooltipTrigger>
            <TooltipContent side="bottom" sideOffset={8}>
              <p>{t("header.profile")}</p>
            </TooltipContent>
          </Tooltip>
        </>
      ) : (
        <>
          <Link to="/login">
            <Button variant="ghost" size="sm" className="h-8 px-2.5 text-xs font-medium leading-none">
              {t("common.signIn")}
            </Button>
          </Link>
          <Link to="/register">
            <Button size="sm" className="h-8 px-3 text-xs font-medium leading-none">
              {t("common.register")}
            </Button>
          </Link>
        </>
      )}
    </div>
  )
}
