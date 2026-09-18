import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { RefreshCw, Scale, ShieldAlert } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState, ErrorState } from "@/components/patterns"
import { useConfirm } from "@/components/ui/alert-dialog"
import { toast } from "@/lib/toast"
import { getErrorDetail } from "@/lib/errorDetail"
import { formatDate } from "@/i18n/format"
import {
  dmcaService,
  type DmcaComplaint,
  type DmcaDecision,
  type DmcaStatus,
} from "@/services/dmca"

/** Written out rather than built from the status, because the i18n key
 *  scanner only finds keys that are spelled in full at the call site. */
const STATUS_LABEL_KEY: Record<DmcaStatus, string> = {
  received: "admin.dmca.status.received",
  upheld: "admin.dmca.status.upheld",
  rejected: "admin.dmca.status.rejected",
  withdrawn: "admin.dmca.status.withdrawn",
}

const STATUS_VARIANT: Record<DmcaStatus, "warningSubtle" | "destructiveSubtle" | "muted"> = {
  received: "warningSubtle",
  upheld: "destructiveSubtle",
  rejected: "muted",
  withdrawn: "muted",
}

/**
 * The complaints ledger.
 *
 * Small on purpose. § 512(i)(1)(A) does not ask for a case-management system;
 * it asks a platform to adopt a repeat-infringer policy, tell people about it,
 * and reasonably implement it — and BMG v. Cox lost the safe harbour holding a
 * thirteen-step written policy whose last step was never taken. Ventura v.
 * Motherless kept it with one person, a simple procedure, and a record.
 *
 * So this screen does exactly three things: show what has arrived, let
 * somebody say whether they agreed with it, and show how many times it has
 * been the same person. The closure at the third upheld complaint is not a
 * button here — the server does it in the same transaction as the decision,
 * because a step somebody has to remember is the step Cox forgot.
 */
export function DmcaTab() {
  const { t } = useTranslation()
  const confirm = useConfirm()
  const [rows, setRows] = useState<DmcaComplaint[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [decidingId, setDecidingId] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(false)
    try {
      setRows(await dmcaService.list())
    } catch {
      setLoadError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const decide = async (row: DmcaComplaint, status: DmcaDecision) => {
    // Upholding the third one closes the account, so the dialog says so
    // before the click rather than a toast saying so afterwards.
    const willClose = status === "upheld" && row.uploaded_by !== null && row.uploader_upheld_count >= 2
    const ok = await confirm({
      title:
        status === "upheld"
          ? t("admin.dmca.confirm.upholdTitle")
          : t("admin.dmca.confirm.rejectTitle"),
      description: willClose
        ? t("admin.dmca.confirm.willCloseAccount", { name: row.uploader_name ?? "" })
        : t("admin.dmca.confirm.body"),
      confirmLabel: t("admin.dmca.confirm.confirm"),
      tone: willClose ? "destructive" : "default",
    })
    if (!ok) return

    setDecidingId(row.id)
    try {
      await dmcaService.decide(row.id, { status, uploader_notified: true })
      toast({ title: t("admin.dmca.toast.recorded"), variant: "success" })
      await load()
    } catch (err) {
      toast({
        title: getErrorDetail(err, t("admin.dmca.toast.failed")),
        variant: "destructive",
      })
    } finally {
      setDecidingId(null)
    }
  }

  return (
    <section className="rounded-md border border-edge bg-card dark:border-transparent">
      <header className="flex items-start justify-between gap-3 border-b border-edge bg-gradient-accent-subtle px-4 py-3">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-medium">
            <Scale className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            {t("admin.dmca.title")}
          </h2>
          <p className="mt-1 text-xs text-ink-muted">{t("admin.dmca.description")}</p>
        </div>
        <Button size="sm" variant="outline" onClick={() => void load()} disabled={loading}>
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          {t("admin.dmca.refresh")}
        </Button>
      </header>

      <div className="divide-y divide-border">
        {loading ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : loadError ? (
          <ErrorState
            className="py-6"
            title={t("admin.dmca.loadError")}
            action={
              <Button size="sm" variant="outline" onClick={() => void load()}>
                {t("common.tryAgain")}
              </Button>
            }
          />
        ) : rows.length === 0 ? (
          <EmptyState
            variant="compact"
            icon={<Scale strokeWidth={1.75} aria-hidden />}
            title={t("admin.dmca.empty.title")}
            description={t("admin.dmca.empty.body")}
          />
        ) : (
          rows.map((row) => (
            <article key={row.id} className="px-4 py-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={STATUS_VARIANT[row.status]}>{t(STATUS_LABEL_KEY[row.status])}</Badge>
                {row.strike_number !== null && (
                  <Badge variant="destructiveSubtle">
                    {t("admin.dmca.strike", { number: row.strike_number })}
                  </Badge>
                )}
                {row.uploader_account_closed && (
                  <Badge variant="destructive">
                    <ShieldAlert className="mr-1 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                    {t("admin.dmca.accountClosed")}
                  </Badge>
                )}
                <span className="text-xs text-ink-muted">{formatDate(row.received_at)}</span>
              </div>

              <p className="mt-2 text-sm">{row.work_described}</p>
              <p className="mt-1 break-all text-xs text-ink-muted">{row.material_location}</p>

              <dl className="mt-3 grid gap-x-6 gap-y-1 text-xs text-ink-muted sm:grid-cols-2">
                <div className="flex gap-1">
                  <dt>{t("admin.dmca.field.complainant")}:</dt>
                  <dd className="text-ink">
                    {row.complainant_name}
                    {row.complainant_organization ? ` · ${row.complainant_organization}` : ""}
                  </dd>
                </div>
                <div className="flex gap-1">
                  <dt>{t("admin.dmca.field.uploader")}:</dt>
                  <dd className="text-ink">
                    {row.uploader_name ?? t("admin.dmca.field.unknownUploader")}
                    {row.uploaded_by !== null && (
                      <>
                        {" · "}
                        {t("admin.dmca.upheldCount", { count: row.uploader_upheld_count })}
                      </>
                    )}
                  </dd>
                </div>
                <div className="flex gap-1">
                  <dt>{t("admin.dmca.field.uploaderTold")}:</dt>
                  <dd className="text-ink">
                    {row.uploader_notified_at
                      ? formatDate(row.uploader_notified_at)
                      : t("admin.dmca.field.notYet")}
                  </dd>
                </div>
                {row.resolution_note && (
                  <div className="flex gap-1 sm:col-span-2">
                    <dt>{t("admin.dmca.field.decision")}:</dt>
                    <dd className="text-ink">{row.resolution_note}</dd>
                  </div>
                )}
              </dl>

              {row.status === "received" && (
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="destructive"
                    disabled={decidingId === row.id}
                    onClick={() => void decide(row, "upheld")}
                  >
                    {t("admin.dmca.action.uphold")}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={decidingId === row.id}
                    onClick={() => void decide(row, "rejected")}
                  >
                    {t("admin.dmca.action.reject")}
                  </Button>
                </div>
              )}
            </article>
          ))
        )}
      </div>
    </section>
  )
}
