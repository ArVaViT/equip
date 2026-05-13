import { useCallback, useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Bell } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { Notification } from "@/types"
import { useNotifications } from "./notifications/useNotifications"
import { NotificationPanel } from "./notifications/NotificationPanel"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

export interface NotificationBellProps {
  /** Full-width panel under the bell inside narrow drawers (e.g. mobile header sheet). */
  panelVariant?: "popover" | "sheet"
  /** Icon-only (header) vs full-width label row (mobile drawer — matches text nav links). */
  triggerVariant?: "icon" | "navRow"
  /** Called when the user opens a notification link (closes parent UI such as the mobile menu). */
  onNotificationNavigate?: () => void
}

/**
 * Header bell: unread badge + on-click dropdown.
 *
 * This component only owns the open/close state and the click-outside
 * behaviour. Everything else (polling, pagination, mutations) lives in
 * `useNotifications`, and the dropdown itself is a pure `NotificationPanel`.
 */
export default function NotificationBell({
  panelVariant = "popover",
  triggerVariant = "icon",
  onNotificationNavigate,
}: NotificationBellProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)

  const {
    notifications,
    unreadCount,
    loading,
    loadingMore,
    loadError,
    hasMore,
    loadMore,
    retry,
    markRead,
    markAllRead,
    remove,
  } = useNotifications(open)

  useEffect(() => {
    if (!open) return
    function handleClickOutside(e: MouseEvent) {
      if (
        panelRef.current && !panelRef.current.contains(e.target as Node) &&
        buttonRef.current && !buttonRef.current.contains(e.target as Node)
      ) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [open])

  const handleActivate = useCallback(
    (n: Notification) => {
      if (!n.is_read) void markRead(n.id)
      setOpen(false)
      onNotificationNavigate?.()
      if (n.link && n.link.startsWith("/")) navigate(n.link)
    },
    [markRead, navigate, onNotificationNavigate],
  )

  const isSheet = panelVariant === "sheet"
  const isNavRow = triggerVariant === "navRow"

  return (
    <div className={cn("relative", isSheet && "w-full")}>
      <Tooltip>
  <TooltipTrigger asChild>
      <Button
        ref={buttonRef}
        variant="ghost"
        size="sm"
        className={cn(
          "relative shadow-none ring-offset-background focus-visible:ring-1",
          isNavRow
            ? "flex h-auto min-h-10 w-full flex-row items-center justify-between rounded-md px-3 py-2 text-left text-sm font-normal hover:bg-muted"
            : "p-0",
          !isNavRow && isSheet && "h-10 min-h-10 w-10 min-w-10",
          !isNavRow && !isSheet && "h-7 w-7",
          isNavRow && open && "bg-muted/80",
        )}
        onClick={() => setOpen((prev) => !prev)}
        aria-label={isNavRow ? undefined : t("notifications.menuAriaLabel")}
        aria-expanded={open}
        aria-haspopup="true"
      >
        {isNavRow ? (
          <>
            <span className="text-sm font-medium text-foreground">{t("notifications.title")}</span>
            <span className="flex min-w-[1.25rem] items-center justify-end">
              {unreadCount > 0 ? (
                <span className="rounded-full bg-destructive px-2 py-0.5 text-xs font-semibold tabular-nums text-destructive-foreground">
                  {unreadCount > 99 ? "99+" : unreadCount}
                </span>
              ) : null}
            </span>
          </>
        ) : (
          <>
            <Bell className="h-3.5 w-3.5" strokeWidth={1.75} />
            {unreadCount > 0 && (
              <span className="absolute -right-0.5 -top-0.5 flex min-h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-xs font-bold leading-none text-destructive-foreground">
                {unreadCount > 99 ? "99+" : unreadCount}
              </span>
            )}
          </>
        )}
      </Button>
        </TooltipTrigger>

  <TooltipContent side="bottom">
    <p>{t("header.notifications")}</p>
  </TooltipContent>
</Tooltip>

      {open && (
        <NotificationPanel
          ref={panelRef}
          variant={panelVariant}
          notifications={notifications}
          unreadCount={unreadCount}
          loading={loading}
          loadingMore={loadingMore}
          loadError={loadError}
          hasMore={hasMore}
          onActivate={handleActivate}
          onDelete={(id) => void remove(id)}
          onMarkAllRead={() => void markAllRead()}
          onLoadMore={loadMore}
          onRetry={retry}
        />
      )}
    </div>
  )
}
