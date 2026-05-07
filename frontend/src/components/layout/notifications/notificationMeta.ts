import {
  Award,
  Bell,
  BookOpen,
  ClipboardCheck,
  Megaphone,
  UserCheck,
  XCircle,
} from "lucide-react"
import type { NotificationType } from "@/types"
import { formatDate } from "@/i18n/format"

/**
 * Icon + colour lookup tables keyed by notification type.
 *
 * Kept here — not in `@/types` — because the icon component set and the
 * Tailwind class palette are presentation concerns specific to the bell
 * dropdown. Consumers that want other mappings (e.g. push notifications)
 * should build their own table rather than import from here.
 */
export const NOTIFICATION_ICONS: Record<NotificationType, typeof Bell> = {
  certificate_approved: Award,
  certificate_rejected: XCircle,
  assignment_graded: ClipboardCheck,
  new_announcement: Megaphone,
  course_update: BookOpen,
  enrollment_confirmed: UserCheck,
}

export const NOTIFICATION_COLORS: Record<NotificationType, string> = {
  certificate_approved: "text-success",
  certificate_rejected: "text-destructive",
  assignment_graded: "text-info",
  new_announcement: "text-warning",
  course_update: "text-muted-foreground",
  enrollment_confirmed: "text-success",
}

/** Compact "x minutes ago" formatter used by the dropdown list. */
export function timeAgo(dateStr: string): string {
  const parsed = new Date(dateStr).getTime()
  if (Number.isNaN(parsed)) return "—"
  const now = Date.now()
  const diff = now - parsed
  const seconds = Math.floor(diff / 1000)
  if (seconds < 60) return "just now"
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return formatDate(dateStr)
}
