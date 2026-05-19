import { useTranslation } from "react-i18next"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { AlertTriangle, Clock, CheckCircle, Mail, XCircle } from "lucide-react"
import { toProxyImage } from "@/lib/images"
import type { ProfileRow } from "./constants"
import { formatDateTime, formatRelative } from "@/i18n/format"

/**
 * Email "credibility" heuristic for the admin's eyeball check. Common
 * disposable / throwaway providers get a destructive warning chip;
 * a free webmail provider gets a muted hint. The absence of any chip
 * (corporate / edu domain) is the green signal. Not a hard gate — just
 * a fast pre-decision hint so the admin doesn't have to parse every
 * email manually.
 */
const DISPOSABLE_DOMAINS = new Set([
  "mailinator.com",
  "tempmail.com",
  "10minutemail.com",
  "guerrillamail.com",
  "throwaway.email",
  "yopmail.com",
])
const FREE_PROVIDERS = new Set([
  "gmail.com",
  "yahoo.com",
  "hotmail.com",
  "outlook.com",
  "mail.ru",
  "yandex.ru",
  "icloud.com",
  "proton.me",
])

function emailDomain(email: string): string {
  const at = email.lastIndexOf("@")
  return at >= 0 ? email.slice(at + 1).toLowerCase() : ""
}

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
        <div className="space-y-3">
          {pending.map((u) => {
            const domain = emailDomain(u.email)
            const disposable = DISPOSABLE_DOMAINS.has(domain)
            const freeProvider = !disposable && FREE_PROVIDERS.has(domain)
            return (
              <article
                key={u.id}
                className="flex flex-col gap-3 rounded-md border border-l-stripe border-l-warning/60 bg-warning/5 p-4 sm:flex-row sm:items-stretch sm:gap-4"
              >
                <div className="flex min-w-0 flex-1 items-start gap-3">
                  {u.avatar_url ? (
                    <img
                      src={toProxyImage(u.avatar_url)}
                      alt={t("admin.users.avatarAltPrefix", { name: u.full_name ?? u.email })}
                      className="h-10 w-10 shrink-0 rounded-full object-cover"
                    />
                  ) : (
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-muted text-sm font-medium text-muted-foreground">
                      {(u.full_name?.[0] ?? u.email[0] ?? "?").toUpperCase()}
                    </div>
                  )}
                  <div className="min-w-0 flex-1 space-y-1">
                    <p className="truncate text-sm font-semibold text-foreground">
                      {u.full_name || t("admin.pendingTeachers.missingName")}
                    </p>
                    <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <Mail className="h-3 w-3 shrink-0" strokeWidth={1.75} aria-hidden />
                      <span className="truncate">{u.email}</span>
                      {disposable && (
                        <Badge variant="destructive" className="ml-1 h-4 px-1 text-[10px] font-medium">
                          <AlertTriangle className="mr-0.5 h-2.5 w-2.5" strokeWidth={2} aria-hidden />
                          {t("admin.pendingTeachers.disposableEmail")}
                        </Badge>
                      )}
                      {freeProvider && (
                        <Badge variant="muted" className="ml-1 h-4 px-1 text-[10px] font-medium">
                          {t("admin.pendingTeachers.freeEmail")}
                        </Badge>
                      )}
                    </p>
                    <p
                      className="flex items-center gap-1.5 text-[11px] text-muted-foreground/80"
                      title={formatDateTime(u.created_at)}
                    >
                      <Clock className="h-3 w-3 shrink-0" strokeWidth={1.75} aria-hidden />
                      {t("admin.pendingTeachers.registeredRelative", {
                        relative: formatRelative(u.created_at),
                      })}
                    </p>
                  </div>
                </div>
                <div className="flex shrink-0 flex-col items-stretch justify-center gap-2 sm:w-44">
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
                  <p className="text-[10px] leading-tight text-muted-foreground/80">
                    {t("admin.pendingTeachers.approveHint")}
                  </p>
                </div>
              </article>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
