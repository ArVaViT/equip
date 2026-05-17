import { Bell, Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import type { Notification } from "@/types"
import { cn } from "@/lib/utils"
import {
  NOTIFICATION_COLORS,
  NOTIFICATION_ICONS,
  timeAgo,
} from "./notificationMeta"

interface Props {
  notification: Notification
  onActivate: (n: Notification) => void
  onDelete: (id: string) => void
}

/**
 * A single row in the bell dropdown. Pure presentation — all side effects
 * live in `useNotifications`.
 */
export function NotificationItem({ notification, onActivate, onDelete }: Props) {
  const { t } = useTranslation()
  const Icon = NOTIFICATION_ICONS[notification.type] ?? Bell
  const color = NOTIFICATION_COLORS[notification.type] ?? "text-muted-foreground"

  return (
    <div
      className={cn(
        "flex gap-3 px-4 py-3 transition-colors hover:bg-muted/50 group border-b border-border/50 last:border-0",
        !notification.is_read && "bg-primary/[0.03]",
      )}
    >
      <button
        onClick={() => onActivate(notification)}
        className="flex gap-3 flex-1 min-w-0 text-left cursor-pointer bg-transparent border-0 p-0"
        aria-label={notification.title}
      >
        <div className={cn("mt-0.5 shrink-0", color)}>
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <p
              className={cn(
                "text-sm leading-snug",
                !notification.is_read
                  ? "font-medium text-foreground"
                  : "text-muted-foreground",
              )}
            >
              {notification.title}
            </p>
            {!notification.is_read && (
              <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary" />
            )}
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">
            {notification.message}
          </p>
          <p className="mt-1 text-xs text-muted-foreground/70">
            {timeAgo(notification.created_at, t)}
          </p>
        </div>
      </button>
      <button
        onClick={(e) => {
          e.stopPropagation()
          onDelete(notification.id)
        }}
        className="mt-0.5 shrink-0 opacity-60 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
        aria-label={t("notifications.deleteAriaLabel")}
      >
        <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} />
      </button>
    </div>
  )
}
