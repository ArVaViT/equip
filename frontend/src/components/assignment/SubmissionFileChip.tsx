import { useCallback, useState } from "react"
import { useTranslation } from "react-i18next"
import { ExternalLink, Loader2, Paperclip } from "lucide-react"
import { storageService } from "@/services/storage"
import { toast } from "@/lib/toast"

/**
 * The file a student handed in, as a chip that opens it.
 *
 * One chip for the three screens that show a submission -- the student's
 * own panel, the teacher's grader and «one by one» marking -- so the file
 * looks the same wherever the work is read. Signed on click, never stored:
 * the row carries `{bucket, path, name}` and the URL is minted against the
 * current secret each time (the rule every private file here follows).
 */
export function SubmissionFileChip({
  bucket,
  path,
  name,
  className = "",
}: {
  bucket: string
  path: string
  name: string
  className?: string
}) {
  const { t } = useTranslation()
  const [opening, setOpening] = useState(false)

  const open = useCallback(async () => {
    if (opening) return
    setOpening(true)
    try {
      const url = await storageService.getSignedSubmissionFileUrl(bucket, path)
      window.open(url, "_blank", "noopener,noreferrer")
    } catch {
      toast({ title: t("toast.openFileFailed"), variant: "destructive" })
    } finally {
      setOpening(false)
    }
  }, [bucket, path, opening, t])

  return (
    <button
      type="button"
      onClick={open}
      disabled={opening}
      aria-label={t("assignment.file.openAria", { name })}
      className={`inline-flex max-w-full min-h-11 items-center gap-2 rounded-lg border border-edge bg-surface px-3 py-2 text-left text-sm hover:bg-muted/40 disabled:opacity-60 ${className}`}
    >
      {opening ? (
        <Loader2 className="h-4 w-4 shrink-0 animate-spin text-ink-muted" strokeWidth={1.75} aria-hidden />
      ) : (
        <Paperclip className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
      )}
      <span className="min-w-0 truncate font-medium">{name}</span>
      <span className="shrink-0 text-ink-muted" aria-hidden>
        ·
      </span>
      <span className="inline-flex shrink-0 items-center gap-1 text-ink-muted">
        {t("assignment.file.open")}
        <ExternalLink className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
      </span>
    </button>
  )
}
