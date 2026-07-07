import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Mail, Plus, RefreshCw } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState, ErrorState } from "@/components/patterns"
import { invitationsService } from "@/services/invitations"
import { toast } from "@/lib/toast"
import { getErrorDetail } from "@/lib/errorDetail"
import { formatDate } from "@/i18n/format"
import { ROLE_I18N_KEY, ROLE_BADGE_VARIANT } from "@/lib/roles"
import type { Invitation, InvitationRole, InvitationStatus } from "@/types"
import { CreateInvitationDialog } from "./CreateInvitationDialog"

// Status shown to the admin is derived: a 'pending' row with is_expired
// renders as its own "Expired" state rather than a misleading "Pending".
type DisplayStatus = InvitationStatus | "expired"

function displayStatus(inv: Invitation): DisplayStatus {
  if (inv.status === "pending" && inv.is_expired) return "expired"
  return inv.status
}

const STATUS_BADGE: Record<DisplayStatus, "successSubtle" | "warningSubtle" | "muted" | "destructiveSubtle"> = {
  pending: "warningSubtle",
  accepted: "successSubtle",
  revoked: "destructiveSubtle",
  expired: "muted",
}

const STATUS_LABEL_KEYS: Record<DisplayStatus, string> = {
  pending: "admin.invitations.statusPending",
  accepted: "admin.invitations.statusAccepted",
  revoked: "admin.invitations.statusRevoked",
  expired: "admin.invitations.statusExpired",
}

type RoleFilterValue = "" | InvitationRole
type StatusFilterValue = "" | "pending" | "accepted" | "revoked"

/** Admin "Invitations" tab: send + track one-time email invites for the
 *  teacher/student roles. Mirrors CohortsTab's card/filter/table shape. */
export function InvitationsTab() {
  const { t } = useTranslation()
  const [invitations, setInvitations] = useState<Invitation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [roleFilter, setRoleFilter] = useState<RoleFilterValue>("")
  const [statusFilter, setStatusFilter] = useState<StatusFilterValue>("")
  const [resendingId, setResendingId] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const reload = useCallback(() => setReloadKey((k) => k + 1), [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    invitationsService
      .listInvitations({
        role: roleFilter || undefined,
        status: statusFilter || undefined,
      })
      .then((data) => {
        if (cancelled) return
        setInvitations(data)
      })
      .catch(() => {
        if (cancelled) return
        setError(t("admin.invitations.loadError"))
      })
      .finally(() => {
        if (cancelled) return
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [roleFilter, statusFilter, reloadKey, t])

  // Re-inviting the same (email, role) is a safe, idempotent resend --
  // see create_or_resend_invitation on the backend. Reuses the same
  // create-invite call; no separate "resend" endpoint exists.
  const handleResend = async (inv: Invitation) => {
    setResendingId(inv.id)
    try {
      await invitationsService.createInvitation(inv.email, inv.role)
      toast({ title: t("admin.invitations.toast.resent"), variant: "success" })
      reload()
    } catch (err) {
      toast({
        title: getErrorDetail(err, t("admin.invitations.toast.resendFailed")),
        variant: "destructive",
      })
    } finally {
      setResendingId(null)
    }
  }

  return (
    <Card className="flex max-h-[calc(100dvh-240px)] flex-col md:max-h-[calc(100dvh-200px)] md:min-h-[420px]">
      <CardHeader className="shrink-0 gap-3 space-y-0 border-b">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-xl">{t("admin.invitations.title")}</CardTitle>
          <Button size="sm" onClick={() => setCreateOpen(true)} className="h-9 shrink-0">
            <Plus className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
            {t("admin.invitations.inviteButton")}
          </Button>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <Select
            value={roleFilter || "all"}
            onValueChange={(v) => setRoleFilter((v === "all" ? "" : v) as InvitationRole)}
          >
            <SelectTrigger size="sm" className="h-9 w-full sm:w-40">
              <SelectValue placeholder={t("admin.invitations.filterRole")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("admin.invitations.allRoles")}</SelectItem>
              <SelectItem value="teacher">{t("roles.teacher")}</SelectItem>
              <SelectItem value="student">{t("roles.student")}</SelectItem>
            </SelectContent>
          </Select>
          <Select
            value={statusFilter || "all"}
            onValueChange={(v) => setStatusFilter((v === "all" ? "" : v) as InvitationStatus)}
          >
            <SelectTrigger size="sm" className="h-9 w-full sm:w-40">
              <SelectValue placeholder={t("admin.invitations.filterStatus")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("admin.invitations.allStatuses")}</SelectItem>
              <SelectItem value="pending">{t("admin.invitations.statusPending")}</SelectItem>
              <SelectItem value="accepted">{t("admin.invitations.statusAccepted")}</SelectItem>
              <SelectItem value="revoked">{t("admin.invitations.statusRevoked")}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col p-0">
        {loading ? (
          <InvitationsTableSkeleton />
        ) : error ? (
          <ErrorState
            title={error}
            action={
              <Button size="sm" variant="outline" onClick={reload}>
                {t("common.tryAgain")}
              </Button>
            }
          />
        ) : invitations.length === 0 ? (
          <div className="flex flex-1 items-center justify-center px-5 py-10">
            <EmptyState
              variant="compact"
              icon={<Mail strokeWidth={1.75} aria-hidden />}
              title={t("admin.invitations.emptyTitle")}
              action={
                <Button size="sm" onClick={() => setCreateOpen(true)}>
                  <Plus className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
                  {t("admin.invitations.inviteButton")}
                </Button>
              }
            />
          </div>
        ) : (
          <InvitationsTable
            items={invitations}
            resendingId={resendingId}
            onResend={handleResend}
          />
        )}
      </CardContent>

      <CreateInvitationDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => {
          setCreateOpen(false)
          reload()
        }}
      />
    </Card>
  )
}

function InvitationsTable({
  items,
  resendingId,
  onResend,
}: {
  items: Invitation[]
  resendingId: string | null
  onResend: (inv: Invitation) => void
}) {
  const { t } = useTranslation()
  return (
    <>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-4 py-3 sm:hidden">
        {items.map((inv) => {
          const status = displayStatus(inv)
          return (
            <div
              key={inv.id}
              className="rounded-md border border-edge dark:border-transparent bg-card p-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink">{inv.email}</p>
                  <p className="mt-1 text-xs text-ink-muted">{formatDate(inv.created_at ?? inv.expires_at)}</p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1.5">
                  <Badge variant={ROLE_BADGE_VARIANT[inv.role]}>{t(ROLE_I18N_KEY[inv.role])}</Badge>
                  <Badge variant={STATUS_BADGE[status]}>{t(STATUS_LABEL_KEYS[status])}</Badge>
                </div>
              </div>
              {(status === "pending" || status === "expired") && (
                <div className="mt-3 flex justify-end">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={resendingId === inv.id}
                    onClick={() => onResend(inv)}
                  >
                    <RefreshCw className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                    {t("admin.invitations.resend")}
                  </Button>
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div className="hidden min-h-0 flex-1 overflow-y-auto sm:block">
        <table className="w-full table-fixed text-sm">
          <colgroup>
            <col className="w-[34%]" />
            <col className="w-[14%]" />
            <col className="w-[16%]" />
            <col className="w-[20%]" />
            <col className="w-[16%]" />
          </colgroup>
          <thead className="sticky top-0 z-10 bg-card">
            <tr className="border-b text-left">
              <th className="px-5 py-3 font-medium text-ink-muted">{t("admin.invitations.thEmail")}</th>
              <th className="px-5 py-3 font-medium text-ink-muted">{t("admin.invitations.thRole")}</th>
              <th className="px-5 py-3 font-medium text-ink-muted">{t("admin.invitations.thStatus")}</th>
              <th className="px-5 py-3 font-medium text-ink-muted">{t("admin.invitations.thSent")}</th>
              <th className="px-5 py-3 font-medium text-ink-muted" />
            </tr>
          </thead>
          <tbody className="divide-y">
            {items.map((inv) => {
              const status = displayStatus(inv)
              return (
                <tr key={inv.id} className="transition-colors hover:bg-muted/40">
                  <td className="truncate px-5 py-3 font-medium" title={inv.email}>
                    {inv.email}
                  </td>
                  <td className="px-5 py-3">
                    <Badge variant={ROLE_BADGE_VARIANT[inv.role]}>{t(ROLE_I18N_KEY[inv.role])}</Badge>
                  </td>
                  <td className="px-5 py-3">
                    <Badge variant={STATUS_BADGE[status]}>{t(STATUS_LABEL_KEYS[status])}</Badge>
                  </td>
                  <td className="px-5 py-3 text-xs text-ink-muted">
                    {formatDate(inv.created_at ?? inv.expires_at)}
                  </td>
                  <td className="px-5 py-3 text-right">
                    {(status === "pending" || status === "expired") && (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={resendingId === inv.id}
                        onClick={() => onResend(inv)}
                      >
                        <RefreshCw className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                        {t("admin.invitations.resend")}
                      </Button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}

function InvitationsTableSkeleton() {
  return (
    <div aria-busy="true">
      <div className="space-y-2 px-4 py-3 sm:hidden">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-md bg-card p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1 space-y-2">
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-3 w-1/2" />
              </div>
              <Skeleton className="h-5 w-16 rounded-full" />
            </div>
          </div>
        ))}
      </div>
      <div className="hidden max-h-[60vh] overflow-y-auto sm:block">
        {Array.from({ length: 6 }).map((_, row) => (
          <div key={row} className="flex items-center gap-4 border-b px-5 py-3">
            {Array.from({ length: 5 }).map((_, col) => (
              <Skeleton key={col} className="h-4 flex-1" />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
