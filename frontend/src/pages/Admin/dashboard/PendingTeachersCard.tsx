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

/** Warning-accented list of users whose role is `pending_teacher`. */
export function PendingTeachersCard({ pending, updatingId, onApprove, onDeny }: Props) {
  const { t } = useTranslation()
  if (pending.length === 0) return null

  return (
    <Card className="mb-8 border-l-stripe border-l-warning">
      <CardHeader>
        <CardTitle className="text-xl flex items-center gap-2">
          <Clock className="h-5 w-5 text-warning" strokeWidth={1.75} aria-hidden />
          {t("admin.pendingTeachers.title")}
          <Badge variant="warning" className="font-normal">
            {pending.length}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {pending.map((u) => (
            <div
              key={u.id}
              className="flex items-center justify-between rounded-md border border-l-stripe border-l-warning/60 bg-warning/5 p-4"
            >
              <div className="flex items-center gap-3 min-w-0">
                {u.avatar_url ? (
                  <img
                    src={toProxyImage(u.avatar_url)}
                    alt={t("admin.users.avatarAltPrefix", { name: u.full_name ?? u.email })}
                    className="h-10 w-10 rounded-full object-cover"
                  />
                ) : (
                  <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center text-sm font-medium text-muted-foreground">
                    {(u.full_name?.[0] ?? u.email[0] ?? "?").toUpperCase()}
                  </div>
                )}
                <div className="min-w-0">
                  <p className="font-medium truncate">{u.full_name || t("admin.pendingTeachers.missingName")}</p>
                  <p className="text-sm text-muted-foreground truncate">{u.email}</p>
                  <p className="text-xs text-muted-foreground">
                    {t("admin.pendingTeachers.registered", { date: formatDate(u.created_at) })}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0 ml-4">
                <Button size="sm" onClick={() => onApprove(u)} disabled={updatingId === u.id}>
                  <CheckCircle className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
                  {t("admin.pendingTeachers.approve")}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onDeny(u)}
                  disabled={updatingId === u.id}
                  className="text-destructive hover:text-destructive"
                >
                  <XCircle className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
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
