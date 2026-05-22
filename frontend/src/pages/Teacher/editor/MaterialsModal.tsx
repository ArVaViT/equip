import type { Ref } from "react"
import { useTranslation } from "react-i18next"
import type { TFunction } from "i18next"
import { Button } from "@/components/ui/button"
import { Download, Loader2, Paperclip, X } from "lucide-react"
import { EmptyState, Modal } from "@/components/patterns"
import type { MaterialFile } from "./types"

interface Props {
  open: boolean
  onClose: () => void
  materials: MaterialFile[]
  uploading: boolean
  onUploadClick: () => void
  onUploadChange: (e: React.ChangeEvent<HTMLInputElement>) => void
  onDownload: (m: MaterialFile) => void
  onDelete: (m: MaterialFile) => void
  fileInputRef: Ref<HTMLInputElement>
}

const ACCEPTED_TYPES = ".pdf,.doc,.docx,.ppt,.pptx,.txt,.mp3,.wav,.ogg,.mp4"

const KB = 1024
const MB = KB * 1024

/**
 * Human-readable file size in the active locale's unit.
 *
 * The previous formatter rendered everything in KB, which produced
 * misleading output at both ends: a 400-byte text snippet showed as
 * ``0 KB`` (rounded down via ``toFixed(0)``) and a 2 MB PDF showed as
 * ``2048 KB``. This picks B / KB / MB so the number always looks
 * sensible at a glance.
 */
function formatFileSize(bytes: number, t: TFunction): string {
  if (bytes < KB) return t("teacherEditor.modals.materials.sizeBytes", { b: bytes })
  if (bytes < MB) return t("teacherEditor.modals.materials.sizeKb", { kb: (bytes / KB).toFixed(0) })
  return t("teacherEditor.modals.materials.sizeMb", { mb: (bytes / MB).toFixed(1) })
}

export function MaterialsModal({
  open,
  onClose,
  materials,
  uploading,
  onUploadClick,
  onUploadChange,
  onDownload,
  onDelete,
  fileInputRef,
}: Props) {
  const { t } = useTranslation()
  return (
    <Modal open={open} onClose={onClose} title={t("teacherEditor.modals.materials.title")}>
      <div className="space-y-4">
        <Button
          variant="outline"
          size="sm"
          className="w-full"
          onClick={onUploadClick}
          disabled={uploading}
        >
          {uploading ? (
            <Loader2 className="h-4 w-4 mr-1.5 animate-spin" strokeWidth={1.75} />
          ) : (
            <Paperclip className="h-4 w-4 mr-1.5" strokeWidth={1.75} />
          )}
          {t("teacherEditor.modals.materials.upload")}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_TYPES}
          className="hidden"
          onChange={onUploadChange}
        />
        {materials.length === 0 ? (
          <EmptyState
            variant="compact"
            icon={<Paperclip strokeWidth={1.75} aria-hidden />}
            title={t("teacherEditor.modals.materials.empty")}
          />
        ) : (
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {materials.map((m) => (
              <div
                key={m.path}
                className="flex items-center gap-3 rounded-md border p-3 transition-colors hover:bg-muted/40"
              >
                <Paperclip className="h-4 w-4 text-muted-foreground shrink-0" strokeWidth={1.75} />
                <span className="text-sm flex-1 truncate">{m.name}</span>
                {m.size && (
                  <span className="text-xs text-muted-foreground shrink-0">
                    {formatFileSize(m.size, t)}
                  </span>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0 shrink-0"
                  onClick={() => onDownload(m)}
                  aria-label={t("teacherEditor.modals.materials.downloadAria", { name: m.name })}
                >
                  <Download className="h-3.5 w-3.5" strokeWidth={1.75} />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0 text-destructive hover:text-destructive shrink-0"
                  onClick={() => onDelete(m)}
                  aria-label={t("teacherEditor.modals.materials.deleteAria", { name: m.name })}
                >
                  <X className="h-3.5 w-3.5" strokeWidth={1.75} />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </Modal>
  )
}
