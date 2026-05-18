import { useTranslation } from "react-i18next"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Clock, CheckCircle, XCircle } from "lucide-react"
import { toProxyImage } from "@/lib/images"
import type { ProfileRow } from "./constants"
import { formatDate } from "@/i18n/format"

interface Props {
  pending: ProfileRow[]
  updatingId: string | null
  onApprove: (user: ProfileRow) => void
  onDeny: (user: ProfileRow) => void
}

/**
 * Warning-accented list of users whose role is ``pending_teacher``.
 *
 * Hidden when there's nothing to action — the card is a real "you
 * need to look at this" surface and an empty state would be noise
 * during a normal admin scan.
 */
export function PendingTeachersCard({ pending, updatingId, onApprove, onDeny }: Props) {
  const { t } = useTranslation()
  if (pending.length === 0) return null

  return (
    <Card className="mb-6 border-l-stripe border-l-warning">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-lg">
          <Clock className="h-4 w-4 text-warning" strokeWidth={1.75} aria-hidden />
          {t("admin.pendingTeachers.title")}
          <Badge variant="warning" className="font-normal">
            {pending.length}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="space-y-2">
          {pending.map((u) => (
            <div
              key={u.id}
              className="flex flex-col gap-3 rounded-md border border-l-stripe border-l-warning/60 bg-warning/5 p-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex min-w-0 items-center gap-3">
                {u.avatar_url ? (
                  <img
                    src={toProxyImage(u.avatar_url)}
                    alt={t("admin.users.avatarAltPrefix", { name: u.full_name ?? u.email })}
                    className="h-9 w-9 shrink-0 rounded-full object-cover"
                  />
                ) : (
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted text-sm font-medium text-muted-foreground">
                    {(u.full_name?.[0] ?? u.email[0] ?? "?").toUpperCase()}
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">
                    {u.full_name || t("admin.pendingTeachers.missingName")}
                  </p>
                  <p className="truncate text-xs text-muted-foreground">{u.email}</p>
                  <p className="text-[11px] text-muted-foreground/80">
                    {t("admin.pendingTeachers.registered", { date: formatDate(u.created_at) })}
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2 sm:ml-4">
                <Button size="sm" className="h-8" onClick={() => onApprove(u)} disabled={updatingId === u.id}>
                  <CheckCircle className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                  {t("admin.pendingTeachers.approve")}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 text-destructive hover:text-destructive"
                  onClick={() => onDeny(u)}
                  disabled={updatingId === u.id}
                >
                  <XCircle className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                  {t("admin.pendingTeachers.deny")}
                </Button>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
