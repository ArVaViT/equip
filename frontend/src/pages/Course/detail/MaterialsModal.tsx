import { useTranslation } from "react-i18next"
import { EmptyState, Modal } from "@/components/patterns"
import { Download, Loader2, Paperclip } from "lucide-react"
import type { CourseMaterial } from "./types"

interface Props {
  open: boolean
  onClose: () => void
  materials: CourseMaterial[]
  downloadingPath: string | null
  onDownload: (path: string) => void
}

export function MaterialsModal({
  open,
  onClose,
  materials,
  downloadingPath,
  onDownload,
}: Props) {
  const { t } = useTranslation()
  return (
    <Modal open={open} onClose={onClose} title={t("courseDetail.materialsModal.title")} size="wide">
      {materials.length === 0 ? (
        <EmptyState
          variant="compact"
          icon={<Paperclip strokeWidth={1.75} aria-hidden />}
          title={t("courseDetail.materialsModal.empty")}
        />
      ) : (
        <div className="divide-y rounded-md border text-sm">
          {materials.map((file) => (
            // The whole row downloads: RUM saw students tap the file's name
            // over and over while only the small icon on the right answered
            // (2026-10-24 → 11-03, every new student of one course).
            <button
              key={file.path}
              type="button"
              disabled={downloadingPath === file.path}
              onClick={() => onDownload(file.path)}
              aria-label={t("teacherEditor.modals.materials.downloadAria", { name: file.name })}
              className="flex w-full items-center justify-between gap-2 px-3 py-3 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand disabled:cursor-wait"
            >
              <span className="min-w-0 flex-1 [overflow-wrap:anywhere]">{file.name}</span>
              <span className="inline-flex h-7 shrink-0 items-center px-2 text-ink-muted" aria-hidden>
                {downloadingPath === file.path ? (
                  <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} />
                ) : (
                  <Download className="h-4 w-4" strokeWidth={1.75} />
                )}
              </span>
            </button>
          ))}
        </div>
      )}
    </Modal>
  )
}
