import { Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import type { Notification } from "@/types"
import { JoinMeetingLink } from "@/components/calendar/JoinMeetingLink"
import { cn } from "@/lib/utils"
import { orNotTranslated } from "@/lib/untranslated"

/** The event's meeting link, when the row is about an event that has one.
 *  `metadata` is `Record<string, unknown>` by declaration — it carries
 *  whatever the emitting route put there — so the value is narrowed to a
 *  string here rather than asserted. `JoinMeetingLink` decides whether it
 *  is a link worth rendering. */
function meetingUrlOf(notification: Notification): string | null {
  const value = notification.metadata?.meeting_url
  return typeof value === "string" ? value : null
}
import {
  colorFor,
  iconFor,
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
  const Icon = iconFor(notification.type)
  const color = colorFor(notification.type)

  return (
    <div
      className={cn(
        "flex gap-3 px-4 py-3 transition-colors hover:bg-muted/50 group border-b border-edge/50 last:border-0",
        !notification.is_read && "bg-brand/[0.03]",
      )}
    >
      <button
        onClick={() => onActivate(notification)}
        className="flex gap-3 flex-1 min-w-0 text-left cursor-pointer bg-transparent border-0 p-0"
        aria-label={orNotTranslated(t, notification.title)}
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
                  ? "font-medium text-ink"
                  : "text-ink-muted",
              )}
            >
              {orNotTranslated(t, notification.title)}
            </p>
            {!notification.is_read && (
              <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand" />
            )}
          </div>
          <p className="mt-0.5 text-xs text-ink-muted line-clamp-2">
            {orNotTranslated(t, notification.message)}
          </p>
          <p className="mt-1 text-xs text-ink-muted">
            {timeAgo(notification.created_at, t)}
          </p>
        </div>
      </button>
      {/* Outside the button, never inside it: a link nested in a button
          is invalid HTML, and browsers recover from it by breaking one
          of the two — usually the link. So the join action is a sibling
          of the row's own click target, sharing its bottom edge. The
          bell is where a student is standing when a session starts, so
          it is worth the row it costs. */}
      <JoinMeetingLink
        url={meetingUrlOf(notification)}
        title={orNotTranslated(t, notification.title)}
        className="self-center"
      />
      <button
        onClick={(e) => {
          e.stopPropagation()
          onDelete(notification.id)
        }}
        className="mt-0.5 shrink-0 opacity-60 group-hover:opacity-100 transition-opacity text-ink-muted hover:text-destructive"
        aria-label={t("notifications.deleteAriaLabel")}
      >
        <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} />
      </button>
    </div>
  )
}
