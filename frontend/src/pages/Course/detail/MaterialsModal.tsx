import { useTranslation } from "react-i18next"
import { EmptyState, Modal } from "@/components/patterns"
import { Button } from "@/components/ui/button"
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
    <Modal open={open} onClose={onClose} title={t("courseDetail.materialsModal.title")}>
      {materials.length === 0 ? (
        <EmptyState
          variant="compact"
          icon={<Paperclip strokeWidth={1.75} aria-hidden />}
          title={t("courseDetail.materialsModal.empty")}
        />
      ) : (
        <div className="divide-y rounded-md border text-sm">
          {materials.map((file) => (
            <div
              key={file.path}
              className="flex items-center justify-between px-3 py-2 transition-colors hover:bg-muted/40"
            >
              <span className="truncate mr-2">{file.name}</span>
              <Button
                variant="ghost"
                size="sm"
                className="shrink-0 h-7 text-xs"
                disabled={downloadingPath === file.path}
                onClick={() => onDownload(file.path)}
              >
                {downloadingPath === file.path ? (
                  <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />
                ) : (
                  <Download className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                )}
              </Button>
            </div>
          ))}
        </div>
      )}
    </Modal>
  )
}
